import asyncio
import base64
import json
import mimetypes
import re
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

import db
from auth import check_password, create_session, is_authenticated
from config import settings
from minecraft import get_players, get_server_status
from rcon_client import execute_rcon
from settings_store import read as read_settings, write as write_settings
from system import get_system_metrics, get_system_metrics_for_record

_live_players: dict[str, str] = {}
_server_online_since: str | None = None


def _server_start_from_log() -> str | None:
    log_path = Path("/logs/latest.log")
    if not log_path.exists():
        return None
    try:
        with open(log_path, errors="replace") as f:
            for line in f:
                m = re.match(r'\[(\d{2}:\d{2}:\d{2})\]', line.strip())
                if m:
                    log_date = datetime.fromtimestamp(
                        log_path.stat().st_ctime, tz=timezone.utc
                    ).date()
                    t = datetime.strptime(m.group(1), "%H:%M:%S").time()
                    return datetime.combine(log_date, t, tzinfo=timezone.utc).isoformat()
    except Exception:
        return None
    return None


async def player_tracker() -> None:
    global _live_players, _server_online_since
    await db.init_db()
    _server_online_since = await db.kv_get("server_online_since")
    if _server_online_since is None:
        from_log = _server_start_from_log()
        if from_log:
            _server_online_since = from_log
            await db.kv_set("server_online_since", from_log)
    while True:
        try:
            current = {p["name"]: p["uuid"] for p in await get_players()}
            for name, uuid in current.items():
                if name not in _live_players:
                    await db.record_event(name, uuid, "join")
            for name, uuid in _live_players.items():
                if name not in current:
                    await db.record_event(name, uuid, "leave")
            _live_players = current
        except Exception as e:
            print(f"[tracker] {e}")
        await asyncio.sleep(30)


async def metrics_recorder() -> None:
    global _server_online_since
    was_online = False
    first = True
    while True:
        if not first:
            await asyncio.sleep(60)
        first = False
        try:
            status, metrics = await asyncio.gather(
                get_server_status(),
                asyncio.to_thread(get_system_metrics_for_record),
            )
            is_online = status.get("online", False)
            if is_online and not was_online:
                _server_online_since = _server_start_from_log() or datetime.now(timezone.utc).isoformat()
                await db.kv_set("server_online_since", _server_online_since)
            elif not is_online and was_online:
                _server_online_since = None
                await db.kv_set("server_online_since", None)
            was_online = is_online
            await db.record_metrics(
                metrics.get("cpu", 0),
                metrics.get("ram_pct", 0),
                status.get("players_online", 0),
                metrics.get("disk_pct", 0),
                metrics.get("net_in_kbs", 0),
                metrics.get("net_out_kbs", 0),
                metrics.get("disk_read_kbs", 0),
                metrics.get("disk_write_kbs", 0),
            )
        except Exception as e:
            print(f"[metrics] {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    t1 = asyncio.create_task(player_tracker())
    t2 = asyncio.create_task(metrics_recorder())
    yield
    t1.cancel()
    t2.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["version"] = Path("VERSION").read_text().strip()


MEDIA_PATH = Path("/data")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    p = MEDIA_PATH / "favicon"
    if not p.exists():
        raise JSONResponse(status_code=404)
    cfg = read_settings()
    return FileResponse(p, media_type=cfg.get("favicon_mime") or "image/png")


@app.get("/media/banner", include_in_schema=False)
async def media_banner():
    p = MEDIA_PATH / "server_banner"
    if not p.exists():
        return JSONResponse(status_code=404, content={})
    cfg = read_settings()
    return FileResponse(p, media_type=cfg.get("banner_mime") or "image/png")


# ── SSE ──────────────────────────────────────────────────────────────────────

@app.get("/stream/dashboard")
async def stream_dashboard(request: Request):
    async def generate():
        while True:
            if await request.is_disconnected():
                break
            status, metrics = await asyncio.gather(
                get_server_status(),
                asyncio.to_thread(get_system_metrics),
            )
            yield {"data": json.dumps({"status": status, "metrics": metrics,
                                       "online_since": _server_online_since})}
            await asyncio.sleep(5)
    return EventSourceResponse(generate())


@app.get("/stream/players")
async def stream_players(request: Request):
    async def generate():
        while True:
            if await request.is_disconnected():
                break
            yield {"data": json.dumps(await get_players())}
            await asyncio.sleep(10)
    return EventSourceResponse(generate())


# ── Pages publiques ───────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    status, metrics = await asyncio.gather(
        get_server_status(),
        asyncio.to_thread(get_system_metrics),
    )
    return templates.TemplateResponse("index.html", {
        "request": request, "status": status, "metrics": metrics,
        "has_banner": (MEDIA_PATH / "server_banner").exists(),
    })


@app.get("/players", response_class=HTMLResponse)
async def players_page(request: Request):
    return templates.TemplateResponse("players.html", {
        "request": request,
        "players": await get_players(),
        "is_admin": is_authenticated(request),
    })


@app.get("/api/player/{uuid}")
async def player_profile(uuid: str):
    def _fetch():
        url = f"https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    try:
        data = await asyncio.to_thread(_fetch)
        skin_type, has_cape = "Steve", False
        for prop in data.get("properties", []):
            if prop["name"] == "textures":
                tex = json.loads(base64.b64decode(prop["value"]))
                if tex.get("textures", {}).get("SKIN", {}).get("metadata", {}).get("model") == "slim":
                    skin_type = "Alex"
                has_cape = "CAPE" in tex.get("textures", {})
        return JSONResponse({"name": data["name"], "uuid": data["id"],
                             "skin_type": skin_type, "has_cape": has_cape})
    except Exception:
        return JSONResponse({"error": "Profil indisponible"}, status_code=404)


@app.post("/players/kick")
async def player_kick(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"error": "Non authentifié"}, status_code=401)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Nom manquant"}, status_code=400)
    cfg = read_settings()
    if not cfg.get("rcon_password"):
        return JSONResponse({"error": "RCON non configuré"}, status_code=503)
    result = await execute_rcon(
        cfg.get("rcon_host") or settings.mc_host,
        cfg.get("rcon_port", 25575),
        cfg["rcon_password"],
        f"kick {name}",
    )
    return JSONResponse({"response": result})


@app.post("/players/ban")
async def player_ban(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"error": "Non authentifié"}, status_code=401)
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        return JSONResponse({"error": "Nom manquant"}, status_code=400)
    cfg = read_settings()
    if not cfg.get("rcon_password"):
        return JSONResponse({"error": "RCON non configuré"}, status_code=503)
    result = await execute_rcon(
        cfg.get("rcon_host") or settings.mc_host,
        cfg.get("rcon_port", 25575),
        cfg["rcon_password"],
        f"ban {name}",
    )
    return JSONResponse({"response": result})


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    player_stats, peak_hours = await asyncio.gather(
        db.get_player_stats(),
        db.get_peak_hours(),
    )
    return templates.TemplateResponse("stats.html", {
        "request": request,
        "player_stats": player_stats,
        "peak_hours": peak_hours,
    })


@app.get("/api/metrics/history")
async def metrics_history(hours: int = 24):
    return JSONResponse(await db.get_metrics_history(hours))


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, days: int = 7):
    return templates.TemplateResponse("history.html", {
        "request": request,
        "events": await db.get_events(limit=200, days=days),
        "days": days,
    })


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    try:
        lines = Path(settings.mc_log_path).read_text(errors="replace").splitlines()[-100:]
    except Exception:
        lines = ["Fichier de log inaccessible."]
    return templates.TemplateResponse("logs.html", {
        "request": request, "lines": lines,
    })


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: bool = False):
    if is_authenticated(request):
        return RedirectResponse("/settings", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if check_password(password):
        response = RedirectResponse("/settings", status_code=302)
        create_session(response)
        return response
    return RedirectResponse("/login?error=1", status_code=302)


@app.get("/logout")
async def logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie("mc_session")
    return response


# ── Pages admin ───────────────────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: bool = False):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("settings.html", {
        "request": request, "cfg": read_settings(),
        "saved": saved, "mc_host": settings.mc_host,
        "has_banner": (MEDIA_PATH / "server_banner").exists(),
        "has_favicon": (MEDIA_PATH / "favicon").exists(),
    })


@app.post("/settings")
async def settings_save(
    request: Request,
    webhook_url: str = Form(""),
    poll_delay: int = Form(60),
    rcon_host: str = Form(""),
    rcon_port: int = Form(25575),
    rcon_password: str = Form(""),
    banner_file: UploadFile = File(None),
    favicon_file: UploadFile = File(None),
    remove_banner: str = Form(""),
    remove_favicon: str = Form(""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    cfg_update: dict = {
        "webhook_url": webhook_url.strip(),
        "poll_delay": max(10, poll_delay),
        "rcon_host": rcon_host.strip() or settings.mc_host,
        "rcon_port": rcon_port,
        "rcon_password": rcon_password,
    }

    if remove_banner:
        (MEDIA_PATH / "server_banner").unlink(missing_ok=True)
        cfg_update["banner_mime"] = ""
    elif banner_file and banner_file.filename:
        content = await banner_file.read()
        if content:
            (MEDIA_PATH / "server_banner").write_bytes(content)
            cfg_update["banner_mime"] = mimetypes.guess_type(banner_file.filename)[0] or "image/png"

    if remove_favicon:
        (MEDIA_PATH / "favicon").unlink(missing_ok=True)
        cfg_update["favicon_mime"] = ""
    elif favicon_file and favicon_file.filename:
        content = await favicon_file.read()
        if content:
            (MEDIA_PATH / "favicon").write_bytes(content)
            cfg_update["favicon_mime"] = mimetypes.guess_type(favicon_file.filename)[0] or "image/png"

    write_settings(cfg_update)
    return RedirectResponse("/settings?saved=1", status_code=302)


@app.get("/console", response_class=HTMLResponse)
async def console_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    cfg = read_settings()
    return templates.TemplateResponse("console.html", {
        "request": request,
        "rcon_configured": bool(cfg.get("rcon_password")),
    })


@app.post("/console/exec")
async def console_exec(request: Request):
    if not is_authenticated(request):
        return JSONResponse({"error": "Non authentifié"}, status_code=401)
    body = await request.json()
    command = body.get("command", "").strip()
    if not command:
        return JSONResponse({"error": "Commande vide"})
    cfg = read_settings()
    if not cfg.get("rcon_password"):
        return JSONResponse({"error": "RCON non configuré — renseignez le mot de passe dans Config."})
    response = await execute_rcon(
        cfg.get("rcon_host") or settings.mc_host,
        cfg.get("rcon_port", 25575),
        cfg["rcon_password"],
        command,
    )
    return JSONResponse({"response": response})

import asyncio
import base64
import json
import urllib.request
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

import db
from auth import check_password, create_session, is_authenticated
from config import settings
from minecraft import get_players, get_server_status
from rcon_client import execute_rcon
from settings_store import read as read_settings, write as write_settings
from system import get_system_metrics

_live_players: dict[str, str] = {}
_server_online_since: str | None = None


async def player_tracker() -> None:
    global _live_players
    await db.init_db()
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
    while True:
        await asyncio.sleep(300)
        try:
            status, metrics = await asyncio.gather(
                get_server_status(),
                asyncio.to_thread(get_system_metrics),
            )
            is_online = status.get("online", False)
            if is_online and not was_online:
                _server_online_since = datetime.now(timezone.utc).isoformat()
            elif not is_online:
                _server_online_since = None
            was_online = is_online
            await db.record_metrics(
                metrics.get("cpu", 0),
                metrics.get("ram_pct", 0),
                status.get("players_online", 0),
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


@app.get("/health")
async def health():
    return {"status": "ok"}


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
    })


@app.post("/settings")
async def settings_save(
    request: Request,
    webhook_url: str = Form(""),
    poll_delay: int = Form(60),
    rcon_host: str = Form(""),
    rcon_port: int = Form(25575),
    rcon_password: str = Form(""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    write_settings({
        "webhook_url": webhook_url.strip(),
        "poll_delay": max(10, poll_delay),
        "rcon_host": rcon_host.strip() or settings.mc_host,
        "rcon_port": rcon_port,
        "rcon_password": rcon_password,
    })
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

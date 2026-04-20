import asyncio
import json
from contextlib import asynccontextmanager
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(player_tracker())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


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
            yield {"data": json.dumps({"status": status, "metrics": metrics})}
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
        "request": request, "players": await get_players(),
    })


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

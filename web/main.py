import asyncio
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from auth import check_password, create_session, is_authenticated
from config import settings
from minecraft import get_players, get_server_status
from settings_store import read as read_settings, write as write_settings
from system import get_system_metrics

app = FastAPI(docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.get("/health")
async def health():
    return {"status": "ok"}


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


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    try:
        lines = Path(settings.mc_log_path).read_text(errors="replace").splitlines()[-100:]
    except Exception:
        lines = ["Fichier de log inaccessible."]
    return templates.TemplateResponse("logs.html", {
        "request": request, "lines": lines,
    })


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


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, saved: bool = False):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("settings.html", {
        "request": request, "cfg": read_settings(), "saved": saved,
    })


@app.post("/settings")
async def settings_save(
    request: Request,
    webhook_url: str = Form(""),
    poll_delay: int = Form(60),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    write_settings({"webhook_url": webhook_url.strip(), "poll_delay": max(10, poll_delay)})
    return RedirectResponse("/settings?saved=1", status_code=302)

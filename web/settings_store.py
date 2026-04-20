import json
from pathlib import Path
from config import settings

_path = Path(settings.settings_path)
_defaults: dict = {
    "webhook_url": "",
    "poll_delay": 60,
    "rcon_host": "",
    "rcon_port": 25575,
    "rcon_password": "",
    "banner_mime": "",
    "favicon_mime": "",
    "discord_server_url": "",
}


def read() -> dict:
    try:
        return {**_defaults, **json.loads(_path.read_text())}
    except Exception:
        return dict(_defaults)


def write(data: dict) -> None:
    _path.parent.mkdir(parents=True, exist_ok=True)
    tmp = _path.with_suffix(".tmp")
    tmp.write_text(json.dumps({**read(), **data}, indent=2))
    tmp.replace(_path)

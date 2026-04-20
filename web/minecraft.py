from mcstatus import JavaServer
from config import settings


async def _status():
    return await JavaServer(settings.mc_host, settings.mc_port).async_status()


async def get_server_status() -> dict:
    try:
        s = await _status()
        return {
            "online": True,
            "players_online": s.players.online,
            "players_max": s.players.max,
            "version": s.version.name,
            "latency": round(s.latency, 1),
            "motd": str(s.motd.to_plain()) if hasattr(s.motd, "to_plain") else str(s.motd),
        }
    except Exception:
        return {"online": False, "players_online": 0, "players_max": 0, "version": "-", "latency": 0, "motd": "-"}


async def get_players() -> list[dict]:
    try:
        s = await _status()
        return [{"name": p.name, "uuid": p.id} for p in (s.players.sample or [])]
    except Exception:
        return []

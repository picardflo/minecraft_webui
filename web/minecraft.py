import aiohttp
from mcstatus import JavaServer
from config import settings


async def get_server_status() -> dict:
    server = JavaServer(settings.mc_host, settings.mc_port)
    try:
        status = await server.async_status()
        return {
            "online": True,
            "players_online": status.players.online,
            "players_max": status.players.max,
            "version": status.version.name,
            "latency": round(status.latency, 1),
            "motd": str(status.motd.to_plain()) if hasattr(status.motd, "to_plain") else str(status.motd),
        }
    except Exception:
        return {"online": False, "players_online": 0, "players_max": 0, "version": "-", "latency": 0, "motd": "-"}


async def get_players() -> list[dict]:
    server = JavaServer(settings.mc_host, settings.mc_port)
    try:
        query = await server.async_query()
        names = query.players.names or []
    except Exception:
        return []

    async with aiohttp.ClientSession() as session:
        results = []
        for name in names:
            uuid = await _fetch_uuid(session, name)
            results.append({"name": name, "uuid": uuid})
        return results


async def _fetch_uuid(session: aiohttp.ClientSession, username: str) -> str | None:
    try:
        async with session.get(
            f"https://api.mojang.com/users/profiles/minecraft/{username}",
            timeout=aiohttp.ClientTimeout(total=5),
        ) as resp:
            if resp.status == 200:
                return (await resp.json()).get("id")
    except Exception:
        pass
    return None

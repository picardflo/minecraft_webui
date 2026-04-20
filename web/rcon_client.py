import asyncio
from mcrcon import MCRcon


async def execute_rcon(host: str, port: int, password: str, command: str) -> str:
    def _run() -> str:
        with MCRcon(host, password, port=port, timeout=5) as mcr:
            return mcr.command(command) or "(pas de réponse)"
    try:
        return await asyncio.to_thread(_run)
    except Exception as e:
        return f"Erreur RCON : {e}"

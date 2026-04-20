import asyncio
import json
import os
from pathlib import Path
from typing import Optional

import aiohttp
from mcstatus import JavaServer
from mcstatus.status_response import JavaStatusPlayer

MC_HOST = os.environ["MC_HOST"]
MC_PORT = int(os.getenv("MC_PORT", "25565"))
SETTINGS_PATH = Path(os.getenv("SETTINGS_PATH", "/data/settings.json"))

previous_players: dict[str, str] = {}  # name -> uuid


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_PATH.read_text())
    except Exception:
        return {"webhook_url": "", "poll_delay": 60}


async def get_online_players() -> dict[str, str]:
    try:
        s = await JavaServer(MC_HOST, MC_PORT).async_status()
        return {p.name: p.id for p in (s.players.sample or [])}
    except Exception:
        return {}


async def send_notification(
    session: aiohttp.ClientSession,
    webhook_url: str,
    username: str,
    uuid: Optional[str],
    joined: bool,
    online_count: int,
) -> None:
    embed: dict = {
        "title": username,
        "description": "a rejoint le serveur" if joined else "a quitté le serveur",
        "color": 0x3BA55C if joined else 0xED4245,
        "footer": {"text": f"{online_count} joueur(s) en ligne"},
    }
    if uuid:
        embed["thumbnail"] = {"url": f"https://mc-heads.net/avatar/{uuid}.png"}
    try:
        async with session.post(webhook_url, json={"embeds": [embed]}) as resp:
            if resp.status not in (200, 204):
                print(f"[webhook] erreur {resp.status}")
    except Exception as e:
        print(f"[webhook] {e}")


async def main() -> None:
    global previous_players
    print(f"Démarrage — surveillance de {MC_HOST}:{MC_PORT}")

    async with aiohttp.ClientSession() as session:
        while True:
            cfg = load_settings()
            webhook_url: str = cfg.get("webhook_url", "")
            poll_delay: int = max(10, cfg.get("poll_delay", 60))

            current_players = await get_online_players()
            joined = {n: u for n, u in current_players.items() if n not in previous_players}
            left   = {n: u for n, u in previous_players.items() if n not in current_players}

            if webhook_url:
                for name, uuid in {**joined, **left}.items():
                    await send_notification(
                        session, webhook_url, name, uuid,
                        name in joined, len(current_players),
                    )

            previous_players = current_players
            await asyncio.sleep(poll_delay)


if __name__ == "__main__":
    asyncio.run(main())

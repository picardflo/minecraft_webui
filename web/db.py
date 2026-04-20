import aiosqlite
from pathlib import Path

DB_PATH = Path("/data/history.db")


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                player    TEXT    NOT NULL,
                uuid      TEXT,
                type      TEXT    NOT NULL,
                timestamp DATETIME DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def record_event(player: str, uuid: str | None, event_type: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events (player, uuid, type) VALUES (?, ?, ?)",
            (player, uuid, event_type),
        )
        await db.commit()


async def get_events(limit: int = 200, days: int | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if days:
            async with db.execute(
                "SELECT * FROM events WHERE timestamp > datetime('now', ?) ORDER BY timestamp DESC LIMIT ?",
                (f"-{days} days", limit),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (limit,)
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

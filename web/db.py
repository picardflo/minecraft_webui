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
        await db.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp  DATETIME DEFAULT (datetime('now')),
                cpu        REAL,
                ram_pct    REAL,
                players    INTEGER,
                disk_pct   REAL,
                net_in     REAL,
                net_out    REAL,
                disk_read  REAL,
                disk_write REAL
            )
        """)
        for col in ("disk_pct", "net_in", "net_out", "disk_read", "disk_write"):
            try:
                await db.execute(f"ALTER TABLE metrics ADD COLUMN {col} REAL DEFAULT 0")
            except Exception:
                pass
        await db.execute("""
            CREATE TABLE IF NOT EXISTS kv (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.commit()


async def kv_get(key: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM kv WHERE key = ?", (key,)) as cur:
            row = await cur.fetchone()
            return row[0] if row else None


async def kv_set(key: str, value: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        if value is None:
            await db.execute("DELETE FROM kv WHERE key = ?", (key,))
        else:
            await db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)", (key, value))
        await db.commit()


async def record_event(player: str, uuid: str | None, event_type: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events (player, uuid, type) VALUES (?, ?, ?)",
            (player, uuid, event_type),
        )
        await db.commit()


async def record_metrics(cpu: float, ram_pct: float, players: int,
                         disk_pct: float = 0, net_in: float = 0, net_out: float = 0,
                         disk_read: float = 0, disk_write: float = 0) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO metrics (cpu, ram_pct, players, disk_pct, net_in, net_out, disk_read, disk_write) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cpu, ram_pct, players, disk_pct, net_in, net_out, disk_read, disk_write),
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


async def get_metrics_history(hours: int = 24) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT timestamp, cpu, ram_pct, players, disk_pct, net_in, net_out, disk_read, disk_write "
            "FROM metrics WHERE timestamp >= datetime('now', ?) ORDER BY timestamp ASC",
            (f"-{hours} hours",),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def get_player_stats() -> list[dict]:
    from datetime import datetime
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT player, uuid, type, timestamp FROM events ORDER BY player, timestamp ASC"
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    players: dict[str, dict] = {}
    pending_join: dict[str, str] = {}

    for r in rows:
        name, uuid, etype, ts = r["player"], r["uuid"], r["type"], r["timestamp"]
        if name not in players:
            players[name] = {"player": name, "uuid": uuid, "sessions": 0, "total_seconds": 0}
        if etype == "join":
            players[name]["sessions"] += 1
            pending_join[name] = ts
        elif etype == "leave" and name in pending_join:
            try:
                j = datetime.fromisoformat(pending_join.pop(name))
                l = datetime.fromisoformat(ts)
                players[name]["total_seconds"] += int((l - j).total_seconds())
            except Exception:
                pass

    return sorted(players.values(), key=lambda x: x["total_seconds"], reverse=True)


async def get_peak_hours() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT strftime('%H', timestamp) as hour, COUNT(*) as count "
            "FROM events WHERE type = 'join' GROUP BY hour ORDER BY hour ASC"
        ) as cur:
            rows = {r["hour"]: r["count"] for r in await cur.fetchall()}
    return [{"hour": f"{h:02d}h", "count": rows.get(f"{h:02d}", 0)} for h in range(24)]

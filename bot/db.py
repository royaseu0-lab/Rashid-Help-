import json
import time

import aiosqlite

from bot.config import DATABASE_PATH, DEFAULT_FLOOD_LIMIT, DEFAULT_FLOOD_SECONDS

_SCHEMA = """
CREATE TABLE IF NOT EXISTS groups (
    chat_id INTEGER PRIMARY KEY,
    title TEXT DEFAULT '',
    locked INTEGER DEFAULT 0,
    rules TEXT DEFAULT '',
    welcome_enabled INTEGER DEFAULT 0,
    welcome_text TEXT DEFAULT '',
    antilink INTEGER DEFAULT 0,
    antiflood INTEGER DEFAULT 1,
    flood_limit INTEGER DEFAULT {flood_limit},
    flood_seconds INTEGER DEFAULT {flood_seconds}
);

CREATE TABLE IF NOT EXISTS warns (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS banned (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    reason TEXT DEFAULT '',
    banned_at INTEGER DEFAULT 0,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS muted (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    until INTEGER DEFAULT 0,
    reason TEXT DEFAULT '',
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS blacklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    word TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    triggers TEXT NOT NULL,
    match_type TEXT NOT NULL DEFAULT 'contains',
    content_type TEXT NOT NULL DEFAULT 'text',
    content_text TEXT DEFAULT '',
    file_id TEXT DEFAULT '',
    buttons TEXT DEFAULT ''
);
""".format(flood_limit=DEFAULT_FLOOD_LIMIT, flood_seconds=DEFAULT_FLOOD_SECONDS)


async def init_db() -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript(_SCHEMA)
        await db.commit()


async def ensure_group(chat_id: int, title: str = "") -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO groups (chat_id, title) VALUES (?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title",
            (chat_id, title),
        )
        await db.commit()


async def get_group(chat_id: int) -> dict:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
        row = await cur.fetchone()
        if row is None:
            await ensure_group(chat_id)
            cur = await db.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
            row = await cur.fetchone()
        return dict(row)


async def set_group_field(chat_id: int, field: str, value) -> None:
    allowed = {
        "locked",
        "rules",
        "welcome_enabled",
        "welcome_text",
        "antilink",
        "antiflood",
        "flood_limit",
        "flood_seconds",
        "title",
    }
    if field not in allowed:
        raise ValueError(f"Field not allowed: {field}")
    await ensure_group(chat_id)
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(f"UPDATE groups SET {field} = ? WHERE chat_id = ?", (value, chat_id))
        await db.commit()


async def count_groups() -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM groups")
        (n,) = await cur.fetchone()
        return n


async def all_group_ids() -> list[int]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT chat_id FROM groups")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


# --- warns ---

async def add_warn(chat_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO warns (chat_id, user_id, count) VALUES (?, ?, 1) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET count = count + 1",
            (chat_id, user_id),
        )
        await db.commit()
        cur = await db.execute(
            "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        (count,) = await cur.fetchone()
        return count


async def remove_warn(chat_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        row = await cur.fetchone()
        if not row:
            return 0
        new_count = max(0, row[0] - 1)
        await db.execute(
            "UPDATE warns SET count = ? WHERE chat_id = ? AND user_id = ?",
            (new_count, chat_id, user_id),
        )
        await db.commit()
        return new_count


async def clear_warns(chat_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM warns WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        await db.commit()


async def get_warns(chat_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        row = await cur.fetchone()
        return row[0] if row else 0


# --- banned / muted lists (local records, mirrors Telegram state) ---

async def record_ban(chat_id: int, user_id: int, reason: str = "") -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO banned (chat_id, user_id, reason, banned_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET reason=excluded.reason, "
            "banned_at=excluded.banned_at",
            (chat_id, user_id, reason, int(time.time())),
        )
        await db.commit()


async def remove_ban_record(chat_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM banned WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        await db.commit()


async def list_banned(chat_id: int) -> list[tuple]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, reason FROM banned WHERE chat_id = ?", (chat_id,)
        )
        return await cur.fetchall()


async def record_mute(chat_id: int, user_id: int, until: int, reason: str = "") -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO muted (chat_id, user_id, until, reason) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET until=excluded.until, "
            "reason=excluded.reason",
            (chat_id, user_id, until, reason),
        )
        await db.commit()


async def remove_mute_record(chat_id: int, user_id: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "DELETE FROM muted WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        await db.commit()


async def list_muted(chat_id: int) -> list[tuple]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, until, reason FROM muted WHERE chat_id = ?", (chat_id,)
        )
        return await cur.fetchall()


# --- blacklist words ---

async def add_blacklist_word(chat_id: int, word: str) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT INTO blacklist (chat_id, word) VALUES (?, ?)", (chat_id, word)
        )
        await db.commit()


async def remove_blacklist_word(chat_id: int, word: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "DELETE FROM blacklist WHERE chat_id = ? AND word = ?", (chat_id, word)
        )
        await db.commit()
        return cur.rowcount > 0


async def clear_blacklist(chat_id: int) -> None:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM blacklist WHERE chat_id = ?", (chat_id,))
        await db.commit()


async def list_blacklist(chat_id: int) -> list[str]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT word FROM blacklist WHERE chat_id = ?", (chat_id,)
        )
        rows = await cur.fetchall()
        return [r[0] for r in rows]


# --- custom replies ---

async def add_reply(
    chat_id: int,
    triggers: list[str],
    match_type: str,
    content_type: str,
    content_text: str = "",
    file_id: str = "",
    buttons: list | None = None,
) -> int:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "INSERT INTO replies (chat_id, triggers, match_type, content_type, "
            "content_text, file_id, buttons) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                chat_id,
                "|".join(triggers),
                match_type,
                content_type,
                content_text,
                file_id,
                json.dumps(buttons or []),
            ),
        )
        await db.commit()
        return cur.lastrowid


async def delete_reply_by_trigger(chat_id: int, trigger: str) -> bool:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT id, triggers FROM replies WHERE chat_id = ?", (chat_id,))
        rows = await cur.fetchall()
        for row in rows:
            triggers = row["triggers"].split("|")
            if trigger in triggers:
                await db.execute("DELETE FROM replies WHERE id = ?", (row["id"],))
                await db.commit()
                return True
        return False


async def list_replies(chat_id: int) -> list[dict]:
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM replies WHERE chat_id = ?", (chat_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

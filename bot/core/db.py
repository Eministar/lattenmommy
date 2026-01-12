import os
import json
import aiosqlite
from datetime import datetime, timezone
import time

class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn = None

    async def init(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._create_tables()
        await self._conn.commit()

    async def _create_tables(self):
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            forum_channel_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            summary_message_id INTEGER NOT NULL,
            category_key TEXT NOT NULL,
            status TEXT NOT NULL,
            claimed_by INTEGER,
            created_at TEXT NOT NULL,
            closed_at TEXT,
            rating INTEGER,
            rating_comment TEXT
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_stats (
            user_id INTEGER PRIMARY KEY,
            total_tickets INTEGER NOT NULL
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        await self._conn.execute("""
                                 CREATE TABLE IF NOT EXISTS infractions
                                 (
                                     id
                                     INTEGER
                                     PRIMARY
                                     KEY
                                     AUTOINCREMENT,
                                     guild_id
                                     INTEGER
                                     NOT
                                     NULL,
                                     user_id
                                     INTEGER
                                     NOT
                                     NULL,
                                     moderator_id
                                     INTEGER
                                     NOT
                                     NULL,
                                     action
                                     TEXT
                                     NOT
                                     NULL,
                                     duration_seconds
                                     INTEGER,
                                     reason
                                     TEXT,
                                     created_at
                                     INTEGER
                                     NOT
                                     NULL
                                 )
                                 """)

        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_infractions_user_time ON infractions(guild_id, user_id, created_at)")

        await self._conn.execute("""
                                 CREATE TABLE IF NOT EXISTS log_threads
                                 (
                                     guild_id
                                     INTEGER
                                     NOT
                                     NULL,
                                     forum_id
                                     INTEGER
                                     NOT
                                     NULL,
                                     key
                                     TEXT
                                     NOT
                                     NULL,
                                     thread_id
                                     INTEGER
                                     NOT
                                     NULL,
                                     created_at
                                     INTEGER
                                     NOT
                                     NULL,
                                     PRIMARY
                                     KEY
                                 (
                                     guild_id,
                                     key
                                 )
                                     )
                                 """)

        await self._conn.commit()

    async def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def create_ticket(self, guild_id: int, user_id: int, forum_channel_id: int, thread_id: int, summary_message_id: int, category_key: str):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO tickets (guild_id, user_id, forum_channel_id, thread_id, summary_message_id, category_key, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?);
        """, (guild_id, user_id, forum_channel_id, thread_id, summary_message_id, category_key, created_at))
        await self._conn.execute("""
        INSERT INTO ticket_stats (user_id, total_tickets)
        VALUES (?, 1)
        ON CONFLICT(user_id) DO UPDATE SET total_tickets = total_tickets + 1;
        """, (user_id,))
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def get_open_ticket_by_user(self, guild_id: int, user_id: int):
        cur = await self._conn.execute("""
        SELECT id, thread_id, summary_message_id, status, claimed_by, category_key
        FROM tickets
        WHERE guild_id = ? AND user_id = ? AND status IN ('open','claimed')
        ORDER BY id DESC LIMIT 1;
        """, (guild_id, user_id))
        row = await cur.fetchone()
        return row

    async def get_ticket_by_thread(self, guild_id: int, thread_id: int):
        cur = await self._conn.execute("""
        SELECT id, user_id, thread_id, summary_message_id, status, claimed_by, category_key
        FROM tickets
        WHERE guild_id = ? AND thread_id = ?
        LIMIT 1;
        """, (guild_id, thread_id))
        return await cur.fetchone()

    async def get_ticket(self, ticket_id: int):
        cur = await self._conn.execute("""
        SELECT id, guild_id, user_id, forum_channel_id, thread_id, summary_message_id, category_key, status, claimed_by,
               created_at, closed_at, rating, rating_comment
        FROM tickets WHERE id = ? LIMIT 1;
        """, (ticket_id,))
        return await cur.fetchone()

    async def set_claim(self, ticket_id: int, staff_id: int | None):
        if staff_id is None:
            await self._conn.execute("""
            UPDATE tickets SET claimed_by = NULL, status = 'open'
            WHERE id = ?;
            """, (ticket_id,))
        else:
            await self._conn.execute("""
            UPDATE tickets SET claimed_by = ?, status = 'claimed'
            WHERE id = ?;
            """, (staff_id, ticket_id))
        await self._conn.commit()

    async def close_ticket(self, ticket_id: int):
        closed_at = await self.now_iso()
        await self._conn.execute("""
        UPDATE tickets SET status = 'closed', closed_at = ?
        WHERE id = ?;
        """, (closed_at, ticket_id))
        await self._conn.commit()

    async def set_rating(self, ticket_id: int, rating: int, comment: str | None):
        await self._conn.execute("""
        UPDATE tickets SET rating = ?, rating_comment = ?
        WHERE id = ?;
        """, (rating, comment, ticket_id))
        await self._conn.commit()

    async def get_ticket_count(self, user_id: int) -> int:
        cur = await self._conn.execute("SELECT total_tickets FROM ticket_stats WHERE user_id = ? LIMIT 1;", (user_id,))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

    async def list_tickets(self, limit: int = 200):
        cur = await self._conn.execute("""
        SELECT id, user_id, thread_id, status, claimed_by, created_at, closed_at, rating
        FROM tickets
        ORDER BY id DESC
        LIMIT ?;
        """, (limit,))
        rows = await cur.fetchall()
        return rows

    async def log_event(self, event: str, payload: dict):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO logs (event, payload, created_at)
        VALUES (?, ?, ?);
        """, (event, json.dumps(payload, ensure_ascii=False), created_at))
        await self._conn.commit()


    async def add_infraction(self, guild_id: int, user_id: int, moderator_id: int, action: str,
                             duration_seconds: int | None, reason: str | None) -> int:
        now = int(time.time())
        cur = await self._conn.execute(
            "INSERT INTO infractions(guild_id,user_id,moderator_id,action,duration_seconds,reason,created_at) VALUES(?,?,?,?,?,?,?)",
            (int(guild_id), int(user_id), int(moderator_id), str(action),
             int(duration_seconds) if duration_seconds is not None else None, str(reason) if reason else None, now)
        )
        await self._conn.commit()
        return int(cur.lastrowid)

    async def count_recent_infractions(self, guild_id: int, user_id: int, actions: list[str], since_ts: int) -> int:
        q = ",".join(["?"] * len(actions))
        cur = await self._conn.execute(
            f"SELECT COUNT(*) FROM infractions WHERE guild_id=? AND user_id=? AND created_at>=? AND action IN ({q})",
            (int(guild_id), int(user_id), int(since_ts), *[str(a) for a in actions])
        )
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def get_log_thread(self, guild_id: int, key: str) -> int | None:
        cur = await self._conn.execute(
            "SELECT thread_id FROM log_threads WHERE guild_id=? AND key=?",
            (int(guild_id), str(key))
        )
        row = await cur.fetchone()
        return int(row[0]) if row else None

    async def set_log_thread(self, guild_id: int, forum_id: int, key: str, thread_id: int):
        now = int(time.time())
        await self._conn.execute(
            "INSERT INTO log_threads(guild_id,forum_id,key,thread_id,created_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(guild_id,key) DO UPDATE SET forum_id=excluded.forum_id, thread_id=excluded.thread_id",
            (int(guild_id), int(forum_id), str(key), int(thread_id), now)
        )
        await self._conn.commit()
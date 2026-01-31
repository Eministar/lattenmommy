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
        await self._ensure_ticket_columns()
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
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS ticket_participants (
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            added_by INTEGER,
            added_at INTEGER NOT NULL,
            PRIMARY KEY (ticket_id, user_id)
        );
        """)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_ticket_participants_user ON ticket_participants(user_id)")
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_backups_guild ON backups(guild_id, id)")
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS birthdays (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS birthdays_global (
            user_id INTEGER NOT NULL,
            day INTEGER NOT NULL,
            month INTEGER NOT NULL,
            year INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            code TEXT NOT NULL,
            unlocked_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id, code)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, key)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            avatar TEXT,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at INTEGER NOT NULL,
            guilds_json TEXT NOT NULL,
            created_at INTEGER NOT NULL
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            title TEXT NOT NULL,
            sponsor TEXT,
            description TEXT,
            end_at TEXT NOT NULL,
            winner_count INTEGER NOT NULL,
            conditions_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            entered_at TEXT NOT NULL,
            PRIMARY KEY (giveaway_id, user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            question TEXT NOT NULL,
            options_json TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS poll_votes (
            poll_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            option_index INTEGER NOT NULL,
            voted_at TEXT NOT NULL,
            PRIMARY KEY (poll_id, user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            voice_seconds INTEGER NOT NULL,
            welcome_count INTEGER NOT NULL,
            xp INTEGER NOT NULL,
            level INTEGER NOT NULL,
            last_message_at TEXT,
            last_voice_at TEXT,
            PRIMARY KEY (guild_id, user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS user_channel_stats (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_count INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id, channel_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS user_voice_sessions (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS tempvoice_rooms (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            owner_id INTEGER NOT NULL,
            panel_channel_id INTEGER,
            panel_message_id INTEGER,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        );
        """)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_tempvoice_owner ON tempvoice_rooms(guild_id, owner_id)")
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_stats_guild ON user_stats(guild_id)")
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_channel_stats_user ON user_channel_stats(guild_id, user_id)")
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS counting_states (
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            current_number INTEGER NOT NULL,
            last_user_id INTEGER,
            highscore INTEGER NOT NULL,
            total_counts INTEGER NOT NULL,
            total_fails INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, channel_id)
        );
        """)
        await self._ensure_counting_columns()
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            questions_json TEXT NOT NULL,
            answers_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            closed_at TEXT
        );
        """)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_applications_user ON applications(guild_id, user_id)")
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS wzs_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            decided_by INTEGER,
            decided_at TEXT,
            posted_at TEXT,
            posted_channel_id INTEGER,
            posted_message_id INTEGER
        );
        """)
        await self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_wzs_status ON wzs_submissions(guild_id, status)")
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS seelsorge_threads (
            guild_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            anonymous INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, thread_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS parliament_stats (
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            elected_count INTEGER NOT NULL,
            candidated_count INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS parliament_votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            candidate_ids_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            ended_at TEXT
        );
        """)
        await self._conn.execute("""
        CREATE TABLE IF NOT EXISTS parliament_vote_entries (
            vote_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            candidate_id INTEGER NOT NULL,
            voted_at TEXT NOT NULL,
            PRIMARY KEY (vote_id, user_id)
        );
        """)

        await self._conn.commit()
        await self._ensure_birthdays_global_seed()

    async def _table_has_column(self, table: str, column: str) -> bool:
        cur = await self._conn.execute(f"PRAGMA table_info({table});")
        rows = await cur.fetchall()
        return any(r and str(r[1]) == column for r in rows)

    async def _ensure_column(self, table: str, column: str, definition: str):
        if not await self._table_has_column(table, column):
            await self._conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition};"
            )

    async def _ensure_ticket_columns(self):
        await self._ensure_column("tickets", "priority", "INTEGER DEFAULT 2")
        await self._ensure_column("tickets", "status_label", "TEXT")
        await self._ensure_column("tickets", "last_activity_at", "TEXT")
        await self._ensure_column("tickets", "last_user_message_at", "TEXT")
        await self._ensure_column("tickets", "last_staff_message_at", "TEXT")
        await self._ensure_column("tickets", "first_staff_reply_at", "TEXT")
        await self._ensure_column("tickets", "sla_breached_at", "TEXT")
        await self._ensure_column("tickets", "escalated_level", "INTEGER DEFAULT 0")
        await self._ensure_column("tickets", "escalated_by", "INTEGER")
        await self._ensure_column("tickets", "escalated_at", "TEXT")

    async def _ensure_counting_columns(self):
        await self._ensure_column("counting_states", "last_count_value", "INTEGER")
        await self._ensure_column("counting_states", "last_count_user_id", "INTEGER")
        await self._ensure_column("counting_states", "last_count_at", "TEXT")
        await self._conn.commit()

    async def _ensure_birthdays_global_seed(self):
        try:
            cur = await self._conn.execute("SELECT COUNT(*) FROM birthdays_global;")
            row = await cur.fetchone()
            count = int(row[0]) if row else 0
        except Exception:
            count = 0
        if count:
            return
        try:
            cur = await self._conn.execute(
                "SELECT user_id, day, month, year, created_at FROM birthdays"
            )
            rows = await cur.fetchall()
        except Exception:
            rows = []
        if not rows:
            return
        seen = set()
        for row in rows:
            uid = int(row[0])
            if uid in seen:
                continue
            seen.add(uid)
            await self._conn.execute(
                """
                INSERT OR IGNORE INTO birthdays_global (user_id, day, month, year, created_at)
                VALUES (?, ?, ?, ?, ?);
                """,
                (uid, int(row[1]), int(row[2]), int(row[3]), row[4]),
            )
        await self._conn.commit()

    async def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    async def create_ticket(self, guild_id: int, user_id: int, forum_channel_id: int, thread_id: int, summary_message_id: int, category_key: str):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO tickets (
            guild_id, user_id, forum_channel_id, thread_id, summary_message_id,
            category_key, status, created_at, priority, last_activity_at, last_user_message_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, 2, ?, ?);
        """, (guild_id, user_id, forum_channel_id, thread_id, summary_message_id, category_key, created_at, created_at, created_at))
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
        SELECT id, user_id, thread_id, summary_message_id, status, claimed_by, category_key,
               priority, status_label, escalated_level, escalated_by,
               created_at, closed_at, last_activity_at, last_user_message_at,
               last_staff_message_at, first_staff_reply_at, sla_breached_at
        FROM tickets
        WHERE guild_id = ? AND thread_id = ?
        LIMIT 1;
        """, (guild_id, thread_id))
        return await cur.fetchone()

    async def get_open_ticket_by_participant(self, guild_id: int, user_id: int):
        cur = await self._conn.execute("""
        SELECT t.id, t.thread_id, t.summary_message_id, t.status, t.claimed_by, t.category_key
        FROM tickets t
        JOIN ticket_participants p ON p.ticket_id = t.id
        WHERE t.guild_id = ? AND p.user_id = ? AND t.status IN ('open','claimed')
        ORDER BY t.id DESC LIMIT 1;
        """, (guild_id, user_id))
        row = await cur.fetchone()
        return row

    async def get_ticket(self, ticket_id: int):
        cur = await self._conn.execute("""
        SELECT id, guild_id, user_id, forum_channel_id, thread_id, summary_message_id, category_key, status, claimed_by,
               created_at, closed_at, rating, rating_comment, priority, status_label, escalated_level, escalated_by,
               last_activity_at, last_user_message_at, last_staff_message_at, first_staff_reply_at, sla_breached_at
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

    async def reopen_ticket(self, ticket_id: int):
        await self._conn.execute("""
        UPDATE tickets SET status = 'open', closed_at = NULL
        WHERE id = ?;
        """, (ticket_id,))
        await self._conn.commit()

    async def set_status_label(self, ticket_id: int, status_label: str | None):
        await self._conn.execute("""
        UPDATE tickets SET status_label = ?
        WHERE id = ?;
        """, (status_label, ticket_id))
        await self._conn.commit()

    async def set_priority(self, ticket_id: int, priority: int):
        await self._conn.execute("""
        UPDATE tickets SET priority = ?
        WHERE id = ?;
        """, (priority, ticket_id))
        await self._conn.commit()

    async def set_category_key(self, ticket_id: int, category_key: str):
        await self._conn.execute("""
        UPDATE tickets SET category_key = ?
        WHERE id = ?;
        """, (category_key, ticket_id))
        await self._conn.commit()

    async def set_escalation(self, ticket_id: int, level: int, actor_id: int | None):
        now = await self.now_iso()
        await self._conn.execute("""
        UPDATE tickets SET escalated_level = ?, escalated_by = ?, escalated_at = ?
        WHERE id = ?;
        """, (level, actor_id, now, ticket_id))
        await self._conn.commit()

    async def set_last_activity(self, ticket_id: int, when_iso: str):
        await self._conn.execute("""
        UPDATE tickets SET last_activity_at = ?
        WHERE id = ?;
        """, (when_iso, ticket_id))
        await self._conn.commit()

    async def set_last_user_message(self, ticket_id: int, when_iso: str):
        await self._conn.execute("""
        UPDATE tickets SET last_user_message_at = ?, last_activity_at = ?
        WHERE id = ?;
        """, (when_iso, when_iso, ticket_id))
        await self._conn.commit()

    async def set_last_staff_message(self, ticket_id: int, when_iso: str):
        await self._conn.execute("""
        UPDATE tickets
        SET last_staff_message_at = ?, last_activity_at = ?,
            first_staff_reply_at = COALESCE(first_staff_reply_at, ?)
        WHERE id = ?;
        """, (when_iso, when_iso, when_iso, ticket_id))
        await self._conn.commit()

    async def set_sla_breached(self, ticket_id: int, when_iso: str):
        await self._conn.execute("""
        UPDATE tickets SET sla_breached_at = ?
        WHERE id = ?;
        """, (when_iso, ticket_id))
        await self._conn.commit()

    async def list_active_tickets(self, limit: int = 500):
        cur = await self._conn.execute("""
        SELECT id, guild_id, user_id, thread_id, status, claimed_by, category_key,
               created_at, last_activity_at, last_user_message_at, last_staff_message_at,
               first_staff_reply_at, sla_breached_at, priority, status_label, escalated_level
        FROM tickets
        WHERE status IN ('open','claimed')
        ORDER BY id DESC
        LIMIT ?;
        """, (limit,))
        rows = await cur.fetchall()
        return rows

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

    async def upsert_user_stats(self, guild_id: int, user_id: int):
        await self._conn.execute("""
        INSERT OR IGNORE INTO user_stats (
            guild_id, user_id, message_count, voice_seconds, welcome_count, xp, level
        ) VALUES (?, ?, 0, 0, 0, 0, 0);
        """, (int(guild_id), int(user_id)))
        await self._conn.commit()

    async def increment_message(self, guild_id: int, user_id: int, channel_id: int, xp_delta: int):
        now = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO user_stats (guild_id, user_id, message_count, voice_seconds, welcome_count, xp, level, last_message_at)
        VALUES (?, ?, 1, 0, 0, ?, 0, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            message_count = message_count + 1,
            xp = xp + excluded.xp,
            last_message_at = excluded.last_message_at;
        """, (int(guild_id), int(user_id), int(xp_delta), now))
        await self._conn.execute("""
        INSERT INTO user_channel_stats (guild_id, user_id, channel_id, message_count)
        VALUES (?, ?, ?, 1)
        ON CONFLICT(guild_id, user_id, channel_id) DO UPDATE SET
            message_count = message_count + 1;
        """, (int(guild_id), int(user_id), int(channel_id)))
        await self._conn.commit()

    async def increment_welcome(self, guild_id: int, user_id: int):
        await self._conn.execute("""
        INSERT INTO user_stats (guild_id, user_id, message_count, voice_seconds, welcome_count, xp, level)
        VALUES (?, ?, 0, 0, 1, 0, 0)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            welcome_count = welcome_count + 1;
        """, (int(guild_id), int(user_id)))
        await self._conn.commit()

    async def add_voice_seconds(self, guild_id: int, user_id: int, seconds: int, xp_delta: int):
        now = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO user_stats (guild_id, user_id, message_count, voice_seconds, welcome_count, xp, level, last_voice_at)
        VALUES (?, ?, 0, ?, 0, ?, 0, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            voice_seconds = voice_seconds + excluded.voice_seconds,
            xp = xp + excluded.xp,
            last_voice_at = excluded.last_voice_at;
        """, (int(guild_id), int(user_id), int(seconds), int(xp_delta), now))
        await self._conn.commit()

    async def get_user_stats(self, guild_id: int, user_id: int):
        cur = await self._conn.execute("""
        SELECT guild_id, user_id, message_count, voice_seconds, welcome_count, xp, level, last_message_at, last_voice_at
        FROM user_stats WHERE guild_id = ? AND user_id = ? LIMIT 1;
        """, (int(guild_id), int(user_id)))
        return await cur.fetchone()

    async def set_user_level(self, guild_id: int, user_id: int, level: int):
        await self._conn.execute("""
        UPDATE user_stats SET level = ? WHERE guild_id = ? AND user_id = ?;
        """, (int(level), int(guild_id), int(user_id)))
        await self._conn.commit()

    async def list_user_channel_stats(self, guild_id: int, user_id: int, limit: int = 10):
        cur = await self._conn.execute("""
        SELECT channel_id, message_count
        FROM user_channel_stats
        WHERE guild_id = ? AND user_id = ?
        ORDER BY message_count DESC
        LIMIT ?;
        """, (int(guild_id), int(user_id), int(limit)))
        return await cur.fetchall()

    async def count_users_with_messages_at_least(self, guild_id: int, count: int):
        cur = await self._conn.execute("""
        SELECT COUNT(*) FROM user_stats WHERE guild_id = ? AND message_count >= ?;
        """, (int(guild_id), int(count)))
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def count_users_with_voice_at_least(self, guild_id: int, seconds: int):
        cur = await self._conn.execute("""
        SELECT COUNT(*) FROM user_stats WHERE guild_id = ? AND voice_seconds >= ?;
        """, (int(guild_id), int(seconds)))
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def count_users_in_stats(self, guild_id: int):
        cur = await self._conn.execute("""
        SELECT COUNT(*) FROM user_stats WHERE guild_id = ?;
        """, (int(guild_id),))
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def get_voice_session(self, guild_id: int, user_id: int):
        cur = await self._conn.execute("""
        SELECT channel_id, joined_at FROM user_voice_sessions
        WHERE guild_id = ? AND user_id = ? LIMIT 1;
        """, (int(guild_id), int(user_id)))
        return await cur.fetchone()

    async def set_voice_session(self, guild_id: int, user_id: int, channel_id: int, joined_at: str):
        await self._conn.execute("""
        INSERT INTO user_voice_sessions (guild_id, user_id, channel_id, joined_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            channel_id = excluded.channel_id,
            joined_at = excluded.joined_at;
        """, (int(guild_id), int(user_id), int(channel_id), str(joined_at)))
        await self._conn.commit()

    async def clear_voice_session(self, guild_id: int, user_id: int):
        await self._conn.execute("""
        DELETE FROM user_voice_sessions WHERE guild_id = ? AND user_id = ?;
        """, (int(guild_id), int(user_id)))
        await self._conn.commit()

    async def list_tickets(self, limit: int = 200):
        cur = await self._conn.execute("""
        SELECT id, user_id, thread_id, status, claimed_by, created_at, closed_at, rating
        FROM tickets
        ORDER BY id DESC
        LIMIT ?;
        """, (limit,))
        rows = await cur.fetchall()
        return rows

    async def list_tickets_for_guild(self, guild_id: int, limit: int = 200):
        cur = await self._conn.execute(
            """
            SELECT id, user_id, thread_id, status, claimed_by, created_at, closed_at, rating
            FROM tickets
            WHERE guild_id = ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (int(guild_id), int(limit)),
        )
        rows = await cur.fetchall()
        return rows

    async def list_logs(self, limit: int = 200):
        cur = await self._conn.execute("""
        SELECT id, event, payload, created_at
        FROM logs
        ORDER BY id DESC
        LIMIT ?;
        """, (limit,))
        rows = await cur.fetchall()
        return rows

    async def count_tickets_by_status_for_guild(self, guild_id: int) -> dict:
        cur = await self._conn.execute(
            "SELECT status, COUNT(*) FROM tickets WHERE guild_id = ? GROUP BY status;",
            (int(guild_id),),
        )
        rows = await cur.fetchall()
        out = {"open": 0, "claimed": 0, "closed": 0}
        for r in rows:
            if not r:
                continue
            status = str(r[0])
            count = int(r[1]) if r[1] is not None else 0
            out[status] = count
        out["total"] = int(out.get("open", 0) + out.get("claimed", 0) + out.get("closed", 0))
        return out

    async def count_giveaways(self, guild_id: int | None = None) -> int:
        if guild_id:
            cur = await self._conn.execute(
                "SELECT COUNT(*) FROM giveaways WHERE guild_id = ?;",
                (int(guild_id),),
            )
        else:
            cur = await self._conn.execute("SELECT COUNT(*) FROM giveaways;")
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def count_polls(self, guild_id: int | None = None) -> int:
        if guild_id:
            cur = await self._conn.execute(
                "SELECT COUNT(*) FROM polls WHERE guild_id = ?;",
                (int(guild_id),),
            )
        else:
            cur = await self._conn.execute("SELECT COUNT(*) FROM polls;")
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def count_applications(self, guild_id: int | None = None) -> int:
        if guild_id:
            cur = await self._conn.execute(
                "SELECT COUNT(*) FROM applications WHERE guild_id = ?;",
                (int(guild_id),),
            )
        else:
            cur = await self._conn.execute("SELECT COUNT(*) FROM applications;")
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def create_backup(self, guild_id: int, name: str, payload_json: str):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO backups (guild_id, name, payload_json, created_at)
        VALUES (?, ?, ?, ?);
        """, (int(guild_id), str(name), str(payload_json), created_at))
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def list_backups(self, guild_id: int, limit: int = 50):
        cur = await self._conn.execute("""
        SELECT id, name, created_at
        FROM backups
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT ?;
        """, (int(guild_id), int(limit)))
        rows = await cur.fetchall()
        return rows

    async def get_backup(self, guild_id: int, backup_id: int):
        cur = await self._conn.execute("""
        SELECT id, name, payload_json, created_at
        FROM backups
        WHERE guild_id = ? AND id = ?
        LIMIT 1;
        """, (int(guild_id), int(backup_id)))
        return await cur.fetchone()

    async def get_backup_by_name(self, guild_id: int, name: str):
        cur = await self._conn.execute("""
        SELECT id, name, payload_json, created_at
        FROM backups
        WHERE guild_id = ? AND name = ?
        ORDER BY id DESC
        LIMIT 1;
        """, (int(guild_id), str(name)))
        return await cur.fetchone()

    async def get_latest_backup(self, guild_id: int):
        cur = await self._conn.execute("""
        SELECT id, name, payload_json, created_at
        FROM backups
        WHERE guild_id = ?
        ORDER BY id DESC
        LIMIT 1;
        """, (int(guild_id),))
        return await cur.fetchone()

    async def set_birthday(self, guild_id: int, user_id: int, day: int, month: int, year: int):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO birthdays (guild_id, user_id, day, month, year, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(guild_id, user_id) DO UPDATE SET
            day = excluded.day,
            month = excluded.month,
            year = excluded.year;
        """, (int(guild_id), int(user_id), int(day), int(month), int(year), created_at))
        await self._conn.commit()

    async def remove_birthday(self, guild_id: int, user_id: int):
        await self._conn.execute("""
        DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?;
        """, (int(guild_id), int(user_id)))
        await self._conn.commit()

    async def get_birthday(self, guild_id: int, user_id: int):
        cur = await self._conn.execute("""
        SELECT day, month, year FROM birthdays WHERE guild_id = ? AND user_id = ? LIMIT 1;
        """, (int(guild_id), int(user_id)))
        return await cur.fetchone()

    async def list_birthdays_for_day(self, guild_id: int, day: int, month: int):
        cur = await self._conn.execute("""
        SELECT user_id, day, month, year
        FROM birthdays
        WHERE guild_id = ? AND day = ? AND month = ?;
        """, (int(guild_id), int(day), int(month)))
        return await cur.fetchall()

    async def list_birthdays(self, guild_id: int, limit: int = 20, offset: int = 0):
        cur = await self._conn.execute("""
        SELECT user_id, day, month, year
        FROM birthdays
        WHERE guild_id = ?
        ORDER BY month ASC, day ASC
        LIMIT ? OFFSET ?;
        """, (int(guild_id), int(limit), int(offset)))
        return await cur.fetchall()

    async def count_birthdays(self, guild_id: int):
        cur = await self._conn.execute("""
        SELECT COUNT(*) FROM birthdays WHERE guild_id = ?;
        """, (int(guild_id),))
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def set_birthday_global(self, user_id: int, day: int, month: int, year: int):
        created_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT INTO birthdays_global (user_id, day, month, year, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                day = excluded.day,
                month = excluded.month,
                year = excluded.year;
            """,
            (int(user_id), int(day), int(month), int(year), created_at),
        )
        await self._conn.commit()

    async def remove_birthday_global(self, user_id: int):
        await self._conn.execute(
            "DELETE FROM birthdays_global WHERE user_id = ?;",
            (int(user_id),),
        )
        await self._conn.commit()

    async def get_birthday_global(self, user_id: int):
        cur = await self._conn.execute(
            "SELECT day, month, year FROM birthdays_global WHERE user_id = ? LIMIT 1;",
            (int(user_id),),
        )
        return await cur.fetchone()

    async def list_birthdays_for_day_global(self, day: int, month: int):
        cur = await self._conn.execute(
            """
            SELECT user_id, day, month, year
            FROM birthdays_global
            WHERE day = ? AND month = ?;
            """,
            (int(day), int(month)),
        )
        return await cur.fetchall()

    async def list_birthdays_global(self, limit: int = 20, offset: int = 0):
        cur = await self._conn.execute(
            """
            SELECT user_id, day, month, year
            FROM birthdays_global
            ORDER BY month ASC, day ASC
            LIMIT ? OFFSET ?;
            """,
            (int(limit), int(offset)),
        )
        return await cur.fetchall()

    async def count_birthdays_global(self):
        cur = await self._conn.execute("SELECT COUNT(*) FROM birthdays_global;")
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def add_achievement(self, guild_id: int, user_id: int, code: str):
        unlocked_at = await self.now_iso()
        await self._conn.execute("""
        INSERT OR IGNORE INTO achievements (guild_id, user_id, code, unlocked_at)
        VALUES (?, ?, ?, ?);
        """, (int(guild_id), int(user_id), str(code), unlocked_at))
        await self._conn.commit()

    async def list_achievements(self, guild_id: int, user_id: int):
        cur = await self._conn.execute("""
        SELECT code, unlocked_at FROM achievements WHERE guild_id = ? AND user_id = ?;
        """, (int(guild_id), int(user_id)))
        return await cur.fetchall()

    async def set_guild_config(self, guild_id: int, key: str, value_json: str):
        updated_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO guild_configs (guild_id, key, value_json, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(guild_id, key) DO UPDATE SET
            value_json = excluded.value_json,
            updated_at = excluded.updated_at;
        """, (int(guild_id), str(key), str(value_json), updated_at))
        await self._conn.commit()

    async def get_guild_config(self, guild_id: int, key: str):
        cur = await self._conn.execute("""
        SELECT value_json FROM guild_configs WHERE guild_id = ? AND key = ? LIMIT 1;
        """, (int(guild_id), str(key)))
        row = await cur.fetchone()
        return row[0] if row else None

    async def list_guild_configs(self, guild_id: int):
        cur = await self._conn.execute(
            "SELECT key, value_json FROM guild_configs WHERE guild_id = ?;",
            (int(guild_id),),
        )
        return await cur.fetchall()

    async def list_all_guild_configs(self):
        cur = await self._conn.execute(
            "SELECT guild_id, key, value_json FROM guild_configs;"
        )
        return await cur.fetchall()

    async def delete_guild_configs(self, guild_id: int):
        await self._conn.execute(
            "DELETE FROM guild_configs WHERE guild_id = ?;",
            (int(guild_id),),
        )
        await self._conn.commit()

    async def count_achievement(self, guild_id: int, code: str):
        cur = await self._conn.execute("""
        SELECT COUNT(*) FROM achievements WHERE guild_id = ? AND code = ?;
        """, (int(guild_id), str(code)))
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def create_giveaway(self, guild_id: int, channel_id: int, title: str, sponsor: str | None,
                              description: str | None, end_at: str, winner_count: int,
                              conditions_json: str, created_by: int):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO giveaways (
            guild_id, channel_id, title, sponsor, description, end_at,
            winner_count, conditions_json, created_by, status, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?);
        """, (int(guild_id), int(channel_id), str(title), sponsor, description, str(end_at),
              int(winner_count), str(conditions_json), int(created_by), created_at))
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def set_giveaway_message(self, giveaway_id: int, message_id: int):
        await self._conn.execute("""
        UPDATE giveaways SET message_id = ? WHERE id = ?;
        """, (int(message_id), int(giveaway_id)))
        await self._conn.commit()

    async def get_giveaway(self, giveaway_id: int):
        cur = await self._conn.execute("""
        SELECT id, guild_id, channel_id, message_id, title, sponsor, description, end_at,
               winner_count, conditions_json, created_by, status, created_at
        FROM giveaways WHERE id = ? LIMIT 1;
        """, (int(giveaway_id),))
        return await cur.fetchone()

    async def get_giveaway_by_message(self, guild_id: int, message_id: int):
        cur = await self._conn.execute("""
        SELECT id, guild_id, channel_id, message_id, title, sponsor, description, end_at,
               winner_count, conditions_json, created_by, status, created_at
        FROM giveaways
        WHERE guild_id = ? AND message_id = ? LIMIT 1;
        """, (int(guild_id), int(message_id)))
        return await cur.fetchone()

    async def list_open_giveaways(self, guild_id: int):
        cur = await self._conn.execute("""
        SELECT id, channel_id, message_id, end_at
        FROM giveaways
        WHERE guild_id = ? AND status = 'open';
        """, (int(guild_id),))
        return await cur.fetchall()

    async def close_giveaway(self, giveaway_id: int):
        await self._conn.execute("""
        UPDATE giveaways SET status = 'closed' WHERE id = ?;
        """, (int(giveaway_id),))
        await self._conn.commit()

    async def add_giveaway_entry(self, giveaway_id: int, user_id: int):
        entered_at = await self.now_iso()
        await self._conn.execute("""
        INSERT OR IGNORE INTO giveaway_entries (giveaway_id, user_id, entered_at)
        VALUES (?, ?, ?);
        """, (int(giveaway_id), int(user_id), entered_at))
        await self._conn.commit()

    async def count_giveaway_entries(self, giveaway_id: int):
        cur = await self._conn.execute("""
        SELECT COUNT(*) FROM giveaway_entries WHERE giveaway_id = ?;
        """, (int(giveaway_id),))
        row = await cur.fetchone()
        return int(row[0] if row else 0)

    async def list_giveaway_entries(self, giveaway_id: int):
        cur = await self._conn.execute("""
        SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?;
        """, (int(giveaway_id),))
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows if r and r[0] is not None]

    async def create_poll(self, guild_id: int, channel_id: int, question: str, options_json: str, created_by: int):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO polls (guild_id, channel_id, question, options_json, created_by, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'open', ?);
        """, (int(guild_id), int(channel_id), str(question), str(options_json), int(created_by), created_at))
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def set_poll_message(self, poll_id: int, message_id: int):
        await self._conn.execute("""
        UPDATE polls SET message_id = ? WHERE id = ?;
        """, (int(message_id), int(poll_id)))
        await self._conn.commit()

    async def get_poll(self, poll_id: int):
        cur = await self._conn.execute("""
        SELECT id, guild_id, channel_id, message_id, question, options_json, created_by, status, created_at
        FROM polls WHERE id = ? LIMIT 1;
        """, (int(poll_id),))
        return await cur.fetchone()

    async def add_poll_vote(self, poll_id: int, user_id: int, option_index: int):
        voted_at = await self.now_iso()
        await self._conn.execute("""
        INSERT OR REPLACE INTO poll_votes (poll_id, user_id, option_index, voted_at)
        VALUES (?, ?, ?, ?);
        """, (int(poll_id), int(user_id), int(option_index), voted_at))
        await self._conn.commit()

    async def list_poll_votes(self, poll_id: int):
        cur = await self._conn.execute("""
        SELECT option_index FROM poll_votes WHERE poll_id = ?;
        """, (int(poll_id),))
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows if r and r[0] is not None]

    async def list_open_polls(self):
        cur = await self._conn.execute("""
        SELECT id, guild_id, channel_id, message_id, options_json
        FROM polls
        WHERE status = 'open';
        """)
        return await cur.fetchall()

    async def create_application(self, guild_id: int, user_id: int, thread_id: int, questions: list[str], answers: list[str]):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO applications (guild_id, user_id, thread_id, status, questions_json, answers_json, created_at)
        VALUES (?, ?, ?, 'open', ?, ?, ?);
        """, (int(guild_id), int(user_id), int(thread_id), json.dumps(questions, ensure_ascii=False),
              json.dumps(answers, ensure_ascii=False), created_at))
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def get_application(self, app_id: int):
        cur = await self._conn.execute("""
        SELECT id, guild_id, user_id, thread_id, status, created_at, closed_at
        FROM applications
        WHERE id = ?
        LIMIT 1;
        """, (int(app_id),))
        return await cur.fetchone()

    async def get_application_by_thread(self, guild_id: int, thread_id: int):
        cur = await self._conn.execute("""
        SELECT id, user_id, status
        FROM applications
        WHERE guild_id = ? AND thread_id = ?
        ORDER BY id DESC
        LIMIT 1;
        """, (int(guild_id), int(thread_id)))
        return await cur.fetchone()

    async def set_application_status(self, app_id: int, status: str):
        closed_at = await self.now_iso() if status and status != "open" else None
        await self._conn.execute(
            "UPDATE applications SET status = ?, closed_at = ? WHERE id = ?;",
            (str(status), closed_at, int(app_id)),
        )
        await self._conn.commit()

    async def list_applications(self, limit: int = 200):
        cur = await self._conn.execute("""
        SELECT id, user_id, thread_id, status, created_at, closed_at
        FROM applications
        ORDER BY id DESC
        LIMIT ?;
        """, (limit,))
        rows = await cur.fetchall()
        return rows

    async def list_applications_for_guild(self, guild_id: int, limit: int = 200):
        cur = await self._conn.execute(
            """
            SELECT id, user_id, thread_id, status, created_at, closed_at
            FROM applications
            WHERE guild_id = ?
            ORDER BY id DESC
            LIMIT ?;
            """,
            (int(guild_id), int(limit)),
        )
        rows = await cur.fetchall()
        return rows

    async def create_wzs_submission(
        self,
        guild_id: int,
        user_id: int,
        thread_id: int,
        message_id: int,
        content: str,
    ):
        created_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT INTO wzs_submissions (
                guild_id, user_id, thread_id, message_id, content, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, 'pending', ?);
            """,
            (
                int(guild_id),
                int(user_id),
                int(thread_id),
                int(message_id),
                str(content),
                created_at,
            ),
        )
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def create_seelsorge_thread(
        self,
        guild_id: int,
        thread_id: int,
        user_id: int,
        anonymous: bool,
    ):
        created_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO seelsorge_threads (
                guild_id, thread_id, user_id, anonymous, created_at
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                int(guild_id),
                int(thread_id),
                int(user_id),
                1 if anonymous else 0,
                created_at,
            ),
        )
        await self._conn.commit()

    async def get_seelsorge_thread(self, guild_id: int, thread_id: int):
        cur = await self._conn.execute(
            """
            SELECT guild_id, thread_id, user_id, anonymous, created_at
            FROM seelsorge_threads
            WHERE guild_id = ? AND thread_id = ?
            LIMIT 1;
            """,
            (int(guild_id), int(thread_id)),
        )
        return await cur.fetchone()

    async def get_parliament_stats(self, guild_id: int, user_id: int):
        cur = await self._conn.execute(
            """
            SELECT guild_id, user_id, elected_count, candidated_count
            FROM parliament_stats
            WHERE guild_id = ? AND user_id = ?
            LIMIT 1;
            """,
            (int(guild_id), int(user_id)),
        )
        return await cur.fetchone()

    async def list_parliament_stats(self, guild_id: int, user_ids: list[int]):
        if not user_ids:
            return []
        placeholders = ",".join("?" for _ in user_ids)
        cur = await self._conn.execute(
            f"""
            SELECT guild_id, user_id, elected_count, candidated_count
            FROM parliament_stats
            WHERE guild_id = ? AND user_id IN ({placeholders});
            """,
            (int(guild_id), *[int(uid) for uid in user_ids]),
        )
        return await cur.fetchall()

    async def increment_parliament_candidated(self, guild_id: int, user_id: int, amount: int = 1):
        row = await self.get_parliament_stats(guild_id, user_id)
        elected = int(row[2]) if row else 0
        candidated = int(row[3]) if row else 0
        candidated += int(amount)
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO parliament_stats (guild_id, user_id, elected_count, candidated_count)
            VALUES (?, ?, ?, ?);
            """,
            (int(guild_id), int(user_id), int(elected), int(candidated)),
        )
        await self._conn.commit()

    async def increment_parliament_elected(self, guild_id: int, user_id: int, amount: int = 1):
        row = await self.get_parliament_stats(guild_id, user_id)
        elected = int(row[2]) if row else 0
        candidated = int(row[3]) if row else 0
        elected += int(amount)
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO parliament_stats (guild_id, user_id, elected_count, candidated_count)
            VALUES (?, ?, ?, ?);
            """,
            (int(guild_id), int(user_id), int(elected), int(candidated)),
        )
        await self._conn.commit()

    async def create_parliament_vote(
        self,
        guild_id: int,
        channel_id: int,
        candidate_ids_json: str,
        created_by: int,
    ):
        created_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT INTO parliament_votes (
                guild_id, channel_id, candidate_ids_json, status, created_by, created_at
            )
            VALUES (?, ?, ?, 'open', ?, ?);
            """,
            (int(guild_id), int(channel_id), str(candidate_ids_json), int(created_by), created_at),
        )
        await self._conn.commit()
        cur = await self._conn.execute("SELECT last_insert_rowid();")
        row = await cur.fetchone()
        return int(row[0])

    async def set_parliament_vote_message(self, vote_id: int, message_id: int):
        await self._conn.execute(
            """
            UPDATE parliament_votes SET message_id = ? WHERE id = ?;
            """,
            (int(message_id), int(vote_id)),
        )
        await self._conn.commit()

    async def get_parliament_vote(self, vote_id: int):
        cur = await self._conn.execute(
            """
            SELECT id, guild_id, channel_id, message_id, candidate_ids_json, status, created_by, created_at, ended_at
            FROM parliament_votes
            WHERE id = ?
            LIMIT 1;
            """,
            (int(vote_id),),
        )
        return await cur.fetchone()

    async def get_open_parliament_vote(self, guild_id: int):
        cur = await self._conn.execute(
            """
            SELECT id, guild_id, channel_id, message_id, candidate_ids_json, status, created_by, created_at, ended_at
            FROM parliament_votes
            WHERE guild_id = ? AND status = 'open'
            ORDER BY id DESC
            LIMIT 1;
            """,
            (int(guild_id),),
        )
        return await cur.fetchone()

    async def close_parliament_vote(self, vote_id: int):
        ended_at = await self.now_iso()
        await self._conn.execute(
            """
            UPDATE parliament_votes SET status = 'closed', ended_at = ? WHERE id = ?;
            """,
            (str(ended_at), int(vote_id)),
        )
        await self._conn.commit()

    async def add_parliament_vote_entry(self, vote_id: int, user_id: int, candidate_id: int):
        voted_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT OR IGNORE INTO parliament_vote_entries (vote_id, user_id, candidate_id, voted_at)
            VALUES (?, ?, ?, ?);
            """,
            (int(vote_id), int(user_id), int(candidate_id), str(voted_at)),
        )
        await self._conn.commit()
        return await self.get_parliament_vote_entry(vote_id, user_id)

    async def get_parliament_vote_entry(self, vote_id: int, user_id: int):
        cur = await self._conn.execute(
            """
            SELECT candidate_id FROM parliament_vote_entries WHERE vote_id = ? AND user_id = ? LIMIT 1;
            """,
            (int(vote_id), int(user_id)),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return int(row[0])

    async def count_parliament_vote_entries(self, vote_id: int):
        cur = await self._conn.execute(
            """
            SELECT candidate_id, COUNT(*) FROM parliament_vote_entries
            WHERE vote_id = ?
            GROUP BY candidate_id;
            """,
            (int(vote_id),),
        )
        rows = await cur.fetchall()
        return {int(r[0]): int(r[1]) for r in rows if r and r[0] is not None}

    async def list_open_parliament_votes(self):
        cur = await self._conn.execute(
            """
            SELECT id, guild_id, channel_id, message_id, candidate_ids_json
            FROM parliament_votes
            WHERE status = 'open';
            """,
        )
        return await cur.fetchall()

    async def get_wzs_submission(self, submission_id: int):
        cur = await self._conn.execute(
            """
            SELECT id, guild_id, user_id, thread_id, message_id, content, status,
                   created_at, decided_by, decided_at, posted_at, posted_channel_id, posted_message_id
            FROM wzs_submissions
            WHERE id = ?
            LIMIT 1;
            """,
            (int(submission_id),),
        )
        return await cur.fetchone()

    async def get_wzs_submission_by_thread(self, guild_id: int, thread_id: int):
        cur = await self._conn.execute(
            """
            SELECT id, user_id, message_id, content, status, created_at, decided_by, decided_at,
                   posted_at, posted_channel_id, posted_message_id
            FROM wzs_submissions
            WHERE guild_id = ? AND thread_id = ?
            ORDER BY id DESC
            LIMIT 1;
            """,
            (int(guild_id), int(thread_id)),
        )
        return await cur.fetchone()

    async def set_wzs_status(self, submission_id: int, status: str, actor_id: int | None = None):
        decided_at = await self.now_iso()
        await self._conn.execute(
            """
            UPDATE wzs_submissions
            SET status = ?, decided_by = ?, decided_at = ?
            WHERE id = ?;
            """,
            (
                str(status),
                int(actor_id) if actor_id else None,
                decided_at,
                int(submission_id),
            ),
        )
        await self._conn.commit()

    async def mark_wzs_posted(self, submission_id: int, channel_id: int, message_id: int):
        posted_at = await self.now_iso()
        await self._conn.execute(
            """
            UPDATE wzs_submissions
            SET status = 'posted', posted_at = ?, posted_channel_id = ?, posted_message_id = ?
            WHERE id = ?;
            """,
            (
                posted_at,
                int(channel_id),
                int(message_id),
                int(submission_id),
            ),
        )
        await self._conn.commit()

    async def list_wzs_candidates(self, guild_id: int, limit: int = 200):
        cur = await self._conn.execute(
            """
            SELECT id, user_id, content, thread_id, created_at
            FROM wzs_submissions
            WHERE guild_id = ? AND status = 'accepted'
            ORDER BY created_at ASC
            LIMIT ?;
            """,
            (int(guild_id), int(limit)),
        )
        return await cur.fetchall()

    async def count_tickets_by_status(self) -> dict:
        cur = await self._conn.execute("""
        SELECT status, COUNT(*) FROM tickets GROUP BY status;
        """)
        rows = await cur.fetchall()
        out = {"open": 0, "claimed": 0, "closed": 0}
        for r in rows:
            if not r:
                continue
            status = str(r[0])
            count = int(r[1]) if r[1] is not None else 0
            out[status] = count
        out["total"] = int(out.get("open", 0) + out.get("claimed", 0) + out.get("closed", 0))
        return out

    async def log_event(self, event: str, payload: dict):
        created_at = await self.now_iso()
        await self._conn.execute("""
        INSERT INTO logs (event, payload, created_at)
        VALUES (?, ?, ?);
        """, (event, json.dumps(payload, ensure_ascii=False), created_at))
        await self._conn.commit()

    async def upsert_dashboard_session(
        self,
        session_id: str,
        user_id: int,
        username: str,
        avatar: str | None,
        access_token: str,
        refresh_token: str | None,
        expires_at: int,
        guilds_json: str,
    ):
        created_at = int(time.time())
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO dashboard_sessions
            (session_id, user_id, username, avatar, access_token, refresh_token, expires_at, guilds_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                str(session_id),
                int(user_id),
                str(username),
                str(avatar) if avatar else None,
                str(access_token),
                str(refresh_token) if refresh_token else None,
                int(expires_at),
                str(guilds_json),
                int(created_at),
            ),
        )
        await self._conn.commit()

    async def get_dashboard_session(self, session_id: str):
        cur = await self._conn.execute(
            """
            SELECT session_id, user_id, username, avatar, access_token, refresh_token, expires_at, guilds_json, created_at
            FROM dashboard_sessions
            WHERE session_id = ?
            LIMIT 1;
            """,
            (str(session_id),),
        )
        return await cur.fetchone()

    async def delete_dashboard_session(self, session_id: str):
        await self._conn.execute(
            "DELETE FROM dashboard_sessions WHERE session_id = ?;",
            (str(session_id),),
        )
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

    async def list_infractions(self, guild_id: int, user_id: int, limit: int = 10):
        cur = await self._conn.execute(
            "SELECT id, action, duration_seconds, reason, created_at, moderator_id "
            "FROM infractions WHERE guild_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
            (int(guild_id), int(user_id), int(limit))
        )
        return await cur.fetchall()

    async def get_infraction(self, guild_id: int, case_id: int):
        cur = await self._conn.execute(
            "SELECT id, action, duration_seconds, reason, created_at, moderator_id, user_id "
            "FROM infractions WHERE guild_id=? AND id=? LIMIT 1",
            (int(guild_id), int(case_id))
        )
        return await cur.fetchone()

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

    async def add_ticket_participant(self, ticket_id: int, user_id: int, added_by: int | None = None) -> None:
        now = int(time.time())
        await self._conn.execute(
            "INSERT OR IGNORE INTO ticket_participants(ticket_id,user_id,added_by,added_at) VALUES(?,?,?,?)",
            (int(ticket_id), int(user_id), int(added_by) if added_by else None, now)
        )
        await self._conn.commit()

    async def list_ticket_participants(self, ticket_id: int) -> list[int]:      
        cur = await self._conn.execute(
            "SELECT user_id FROM ticket_participants WHERE ticket_id = ? ORDER BY user_id ASC",
            (int(ticket_id),)
        )
        rows = await cur.fetchall()
        return [int(r[0]) for r in rows if r and r[0] is not None]

    async def create_tempvoice_room(
        self,
        guild_id: int,
        channel_id: int,
        owner_id: int,
        panel_channel_id: int | None,
        panel_message_id: int | None,
    ):
        created_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT OR REPLACE INTO tempvoice_rooms
            (guild_id, channel_id, owner_id, panel_channel_id, panel_message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?);
            """,
            (
                int(guild_id),
                int(channel_id),
                int(owner_id),
                int(panel_channel_id) if panel_channel_id else None,
                int(panel_message_id) if panel_message_id else None,
                created_at,
            ),
        )
        await self._conn.commit()

    async def get_tempvoice_room_by_channel(self, guild_id: int, channel_id: int):
        cur = await self._conn.execute(
            """
            SELECT guild_id, channel_id, owner_id, panel_channel_id, panel_message_id, created_at
            FROM tempvoice_rooms
            WHERE guild_id = ? AND channel_id = ?;
            """,
            (int(guild_id), int(channel_id)),
        )
        return await cur.fetchone()

    async def get_tempvoice_room_by_owner(self, guild_id: int, owner_id: int):
        cur = await self._conn.execute(
            """
            SELECT guild_id, channel_id, owner_id, panel_channel_id, panel_message_id, created_at
            FROM tempvoice_rooms
            WHERE guild_id = ? AND owner_id = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (int(guild_id), int(owner_id)),
        )
        return await cur.fetchone()

    async def list_tempvoice_rooms(self, guild_id: int):
        cur = await self._conn.execute(
            """
            SELECT guild_id, channel_id, owner_id, panel_channel_id, panel_message_id, created_at
            FROM tempvoice_rooms
            WHERE guild_id = ?;
            """,
            (int(guild_id),),
        )
        return await cur.fetchall()

    async def set_tempvoice_owner(self, guild_id: int, channel_id: int, owner_id: int):
        await self._conn.execute(
            """
            UPDATE tempvoice_rooms
            SET owner_id = ?
            WHERE guild_id = ? AND channel_id = ?;
            """,
            (int(owner_id), int(guild_id), int(channel_id)),
        )
        await self._conn.commit()

    async def set_tempvoice_panel_message(
        self,
        guild_id: int,
        channel_id: int,
        panel_channel_id: int | None,
        panel_message_id: int | None,
    ):
        await self._conn.execute(
            """
            UPDATE tempvoice_rooms
            SET panel_channel_id = ?, panel_message_id = ?
            WHERE guild_id = ? AND channel_id = ?;
            """,
            (
                int(panel_channel_id) if panel_channel_id else None,
                int(panel_message_id) if panel_message_id else None,
                int(guild_id),
                int(channel_id),
            ),
        )
        await self._conn.commit()

    async def delete_tempvoice_room(self, guild_id: int, channel_id: int):
        await self._conn.execute(
            "DELETE FROM tempvoice_rooms WHERE guild_id = ? AND channel_id = ?;",
            (int(guild_id), int(channel_id)),
        )
        await self._conn.commit()

    async def get_counting_state(self, guild_id: int, channel_id: int):
        cur = await self._conn.execute(
            """
            SELECT
                guild_id,
                channel_id,
                current_number,
                last_user_id,
                highscore,
                total_counts,
                total_fails,
                updated_at,
                last_count_value,
                last_count_user_id,
                last_count_at
            FROM counting_states
            WHERE guild_id = ? AND channel_id = ?
            LIMIT 1;
            """,
            (int(guild_id), int(channel_id)),
        )
        return await cur.fetchone()

    async def upsert_counting_state(
        self,
        guild_id: int,
        channel_id: int,
        current_number: int,
        last_user_id: int | None,
        highscore: int,
        total_counts: int,
        total_fails: int,
        last_count_value: int | None,
        last_count_user_id: int | None,
        last_count_at: str | None,
    ):
        updated_at = await self.now_iso()
        await self._conn.execute(
            """
            INSERT INTO counting_states
            (
                guild_id,
                channel_id,
                current_number,
                last_user_id,
                highscore,
                total_counts,
                total_fails,
                updated_at,
                last_count_value,
                last_count_user_id,
                last_count_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_id) DO UPDATE SET
                current_number=excluded.current_number,
                last_user_id=excluded.last_user_id,
                highscore=excluded.highscore,
                total_counts=excluded.total_counts,
                total_fails=excluded.total_fails,
                updated_at=excluded.updated_at,
                last_count_value=excluded.last_count_value,
                last_count_user_id=excluded.last_count_user_id,
                last_count_at=excluded.last_count_at;
            """,
            (
                int(guild_id),
                int(channel_id),
                int(current_number),
                int(last_user_id) if last_user_id is not None else None,
                int(highscore),
                int(total_counts),
                int(total_fails),
                updated_at,
                int(last_count_value) if last_count_value is not None else None,
                int(last_count_user_id) if last_count_user_id is not None else None,
                str(last_count_at) if last_count_at is not None else None,
            ),
        )
        await self._conn.commit()

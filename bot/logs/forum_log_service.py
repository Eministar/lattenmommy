from __future__ import annotations

import time
import discord

from bot.utils.emojis import em


class ForumLogService:
    DEFAULT_THREADS: dict[str, str] = {
        "join_leave": "👤 ~ Server-Beitritte & Leaves",
        "message_updates": "💬 ~ Nachricht-Updates",
        "channel_role": "📢 ~ Kanal-& Rollen-Änderungen",
        "punishments": "👮 ~ Bestrafungen",
        "bot_errors": "❌ × Bot Fehlermeldungen",
    }

    def __init__(self, bot: discord.Client, settings, db):
        self.bot = bot
        self.settings = settings
        self.db = db
        self._ready = False
        self._cache: dict[str, int] = {}

    def enabled(self) -> bool:
        return bool(self.settings.get_bool("logs.enabled", True))

    async def start(self):
        if self._ready or not self.enabled():
            return

        guild_id = self.settings.get_int("bot.guild_id")
        forum_id = self.settings.get_int("bot.log_forum_channel_id")
        if not guild_id or not forum_id:
            return

        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return

        forum = guild.get_channel(int(forum_id))
        if not isinstance(forum, discord.ForumChannel):
            return

        for key, title in self.DEFAULT_THREADS.items():
            await self.ensure_thread(forum, guild, key, title)

        self._ready = True

    async def ensure_thread(self, forum: discord.ForumChannel, guild: discord.Guild, key: str, title: str) -> int | None:
        cached = self._cache.get(key)
        if cached:
            return cached

        stored = await self.db.get_log_thread(guild.id, key)
        if stored:
            self._cache[key] = int(stored)
            return int(stored)

        name = title[:100]
        green = em(self.settings, "green", guild) or "🟩"
        content = f"{green} - Dieser Thread postet nun alle **{title}**."

        created = await forum.create_thread(name=name, content=content)
        thread = created.thread
        await self.db.set_log_thread(guild.id, forum.id, key, thread.id)
        self._cache[key] = int(thread.id)
        return int(thread.id)

    async def emit(self, key: str, embed: discord.Embed, content: str | None = None):
        if not self.enabled():
            return

        guild_id = self.settings.get_int("bot.guild_id")
        forum_id = self.settings.get_int("bot.log_forum_channel_id")
        if not guild_id or not forum_id:
            return

        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return

        forum = guild.get_channel(int(forum_id))
        if not isinstance(forum, discord.ForumChannel):
            return

        thread_id = await self.ensure_thread(forum, guild, key, self.DEFAULT_THREADS.get(key, key))
        if not thread_id:
            return

        thread = guild.get_thread(int(thread_id))
        if not thread:
            try:
                fetched = await self.bot.fetch_channel(int(thread_id))
                thread = fetched if isinstance(fetched, discord.Thread) else None
            except Exception:
                thread = None

        if not thread:
            return

        try:
            await thread.send(content=content, embed=embed)
        except Exception:
            pass

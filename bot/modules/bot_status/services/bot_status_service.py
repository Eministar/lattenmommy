from __future__ import annotations

from datetime import datetime, timezone
import discord
from bot.modules.bot_status.formatting.bot_status_embeds import build_bot_status_view


class BotStatusService:
    def __init__(self, bot: discord.Client, settings, logger):
        self.bot = bot
        self.settings = settings
        self.logger = logger
        self.started_at: datetime | None = None
        self._start_sent = False
        self._stop_sent = False

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "bot_status.enabled", True))

    def _channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "bot_status.channel_id", 0) or 0)

    async def _resolve_channel(self, guild: discord.Guild, channel_id: int) -> discord.abc.Messageable | None:
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return None
        if getattr(ch, "guild", None) and ch.guild.id != guild.id:
            return None
        return ch

    def _stats(self) -> tuple[int, int]:
        guilds = list(self.bot.guilds)
        guild_count = len(guilds)
        latency_ms = int(round((self.bot.latency or 0) * 1000))
        return guild_count, latency_ms

    async def send_start(self):
        if self._start_sent:
            return
        self._start_sent = True
        self.started_at = datetime.now(timezone.utc)
        now = self.started_at
        guild_count, latency_ms = self._stats()
        for guild in list(self.bot.guilds):
            if not self._enabled(guild.id):
                continue
            channel_id = self._channel_id(guild.id)
            if not channel_id:
                continue
            ch = await self._resolve_channel(guild, channel_id)
            if not ch:
                continue
            try:
                member_count = int(guild.member_count or len(guild.members))
            except Exception:
                member_count = 0
            view = build_bot_status_view(
                self.settings,
                guild,
                True,
                now,
                self.started_at,
                guild_count,
                member_count,
                latency_ms,
            )
            try:
                await ch.send(view=view)
            except Exception:
                pass

    async def send_stop(self):
        if self._stop_sent:
            return
        self._stop_sent = True
        now = datetime.now(timezone.utc)
        guild_count, latency_ms = self._stats()
        for guild in list(self.bot.guilds):
            if not self._enabled(guild.id):
                continue
            channel_id = self._channel_id(guild.id)
            if not channel_id:
                continue
            ch = await self._resolve_channel(guild, channel_id)
            if not ch:
                continue
            try:
                member_count = int(guild.member_count or len(guild.members))
            except Exception:
                member_count = 0
            view = build_bot_status_view(
                self.settings,
                guild,
                False,
                now,
                self.started_at,
                guild_count,
                member_count,
                latency_ms,
            )
            try:
                await ch.send(view=view)
            except Exception:
                pass

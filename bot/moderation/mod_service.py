from __future__ import annotations

from datetime import datetime, timedelta, timezone
import discord

from bot.moderation.penalty import PenaltyEngine
from bot.utils.mod_formatting import (
    build_timeout_embed,
    build_warn_embed,
    build_kick_embed,
    build_ban_embed,
    build_purge_embed,
)


class ModerationService:
    def __init__(self, bot: discord.Client, settings, db, forum_logs):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.forum_logs = forum_logs
        self.penalty = PenaltyEngine(settings, db)

    async def timeout(self, guild: discord.Guild, moderator: discord.Member, target: discord.Member, minutes: int | None, reason: str | None):
        if minutes is None:
            minutes, strikes = await self.penalty.compute_timeout_minutes(guild.id, target.id)
        else:
            strikes = 1

        until = datetime.now(timezone.utc) + timedelta(minutes=int(minutes))

        ok = False
        err = None

        try:
            if hasattr(target, "timeout"):
                await target.timeout(until, reason=reason or None)
            else:
                await target.edit(timed_out_until=until, reason=reason or None)
            ok = True
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"

        if ok:
            await self.db.add_infraction(guild.id, target.id, moderator.id, "timeout", int(minutes) * 60, reason)

        emb = build_timeout_embed(self.settings, guild, moderator, target, int(minutes), int(strikes), reason)
        if self.forum_logs:
            await self.forum_logs.emit("punishments", emb)

        return ok, err, int(minutes), int(strikes)

    async def warn(self, guild: discord.Guild, moderator: discord.Member, target: discord.Member, reason: str | None):
        strikes = 1
        try:
            from time import time
            since = int(time()) - 30 * 86400
            prev = await self.db.count_recent_infractions(guild.id, target.id, ["warn", "timeout"], since)
            strikes = int(prev + 1)
        except Exception:
            strikes = 1

        await self.db.add_infraction(guild.id, target.id, moderator.id, "warn", None, reason)

        emb = build_warn_embed(self.settings, guild, moderator, target, strikes, reason)
        if self.forum_logs:
            await self.forum_logs.emit("punishments", emb)

        return strikes

    async def kick(self, guild: discord.Guild, moderator: discord.Member, target: discord.Member, reason: str | None):
        ok = False
        err = None

        try:
            await target.kick(reason=reason or None)
            ok = True
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"

        if ok:
            await self.db.add_infraction(guild.id, target.id, moderator.id, "kick", None, reason)

        emb = build_kick_embed(self.settings, guild, moderator, target, reason)
        if self.forum_logs:
            await self.forum_logs.emit("punishments", emb)

        return ok, err

    async def ban(self, guild: discord.Guild, moderator: discord.Member, target: discord.User | discord.Member, delete_days: int, reason: str | None):
        ok = False
        err = None

        dd = int(delete_days)
        if dd < 0:
            dd = 0
        if dd > 7:
            dd = 7

        uid = int(getattr(target, "id", 0))

        try:
            await guild.ban(target, reason=reason or None, delete_message_days=dd)
            ok = True
        except Exception as e:
            ok = False
            err = f"{type(e).__name__}: {e}"

        if ok and uid:
            await self.db.add_infraction(guild.id, uid, moderator.id, "ban", None, reason)

        emb = build_ban_embed(self.settings, guild, moderator, target, dd, reason)
        if self.forum_logs:
            await self.forum_logs.emit("punishments", emb)

        return ok, err, dd

    async def purge(self, guild: discord.Guild, moderator: discord.Member, channel: discord.TextChannel, amount: int, user: discord.Member | None):
        n = int(amount)
        if n < 1:
            n = 1
        if n > 100:
            n = 100

        deleted = 0
        err = None

        def check(m: discord.Message):
            if user:
                return m.author.id == user.id
            return True

        try:
            res = await channel.purge(limit=n, check=check, bulk=True)
            deleted = len(res)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"

        emb = build_purge_embed(self.settings, guild, moderator, channel, deleted, n, user)
        if self.forum_logs:
            await self.forum_logs.emit("punishments", emb)

        if deleted > 0:
            try:
                await self.db.add_infraction(guild.id, (user.id if user else 0), moderator.id, "purge", None, f"deleted={deleted}")
            except Exception:
                pass

        return deleted, err

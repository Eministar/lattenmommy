from __future__ import annotations

import time
import discord
from discord.ext import commands

from bot.utils.mod_formatting import (
    build_channel_created_embed,
    build_channel_deleted_embed,
    build_channel_updated_embed,
    build_role_created_embed,
    build_role_deleted_embed,
    build_role_updated_embed,
    build_member_roles_changed_embed,
)

_AUDIT_WINDOW_SECONDS = 25


class ChannelRoleLogListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _guild_ok(self, guild: discord.Guild | None) -> bool:
        gid = self.bot.settings.get_int("bot.guild_id")
        return bool(guild and gid and guild.id == int(gid))

    async def _find_audit_actor(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int) -> discord.Member | None:
        try:
            now = time.time()
            async for entry in guild.audit_logs(limit=6, action=action):
                if not entry or not entry.target:
                    continue
                tid = getattr(entry.target, "id", None)
                if tid != int(target_id):
                    continue
                created = getattr(entry, "created_at", None)
                if created:
                    age = abs((created.timestamp() - now))
                    if age > _AUDIT_WINDOW_SECONDS:
                        continue
                user = getattr(entry, "user", None)
                if isinstance(user, discord.Member):
                    return user
                if user:
                    m = guild.get_member(getattr(user, "id", 0))
                    return m
        except Exception:
            return None
        return None

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not self._guild_ok(channel.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        actor = None
        if channel.guild.me and channel.guild.me.guild_permissions.view_audit_log:
            actor = await self._find_audit_actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)

        emb = build_channel_created_embed(self.bot.settings, channel.guild, channel, actor)
        await logs.emit("channel_role", emb)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not self._guild_ok(channel.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        actor = None
        if channel.guild.me and channel.guild.me.guild_permissions.view_audit_log:
            actor = await self._find_audit_actor(channel.guild, discord.AuditLogAction.channel_delete, channel.id)

        emb = build_channel_deleted_embed(self.bot.settings, channel.guild, channel, actor)
        await logs.emit("channel_role", emb)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if not self._guild_ok(after.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        actor = None
        if after.guild.me and after.guild.me.guild_permissions.view_audit_log:
            actor = await self._find_audit_actor(after.guild, discord.AuditLogAction.channel_update, after.id)

        emb = build_channel_updated_embed(self.bot.settings, after.guild, before, after, actor)
        if emb:
            await logs.emit("channel_role", emb)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if not self._guild_ok(role.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        actor = None
        if role.guild.me and role.guild.me.guild_permissions.view_audit_log:
            actor = await self._find_audit_actor(role.guild, discord.AuditLogAction.role_create, role.id)

        emb = build_role_created_embed(self.bot.settings, role.guild, role, actor)
        await logs.emit("channel_role", emb)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if not self._guild_ok(role.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        actor = None
        if role.guild.me and role.guild.me.guild_permissions.view_audit_log:
            actor = await self._find_audit_actor(role.guild, discord.AuditLogAction.role_delete, role.id)

        emb = build_role_deleted_embed(self.bot.settings, role.guild, role, actor)
        await logs.emit("channel_role", emb)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if not self._guild_ok(after.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        actor = None
        if after.guild.me and after.guild.me.guild_permissions.view_audit_log:
            actor = await self._find_audit_actor(after.guild, discord.AuditLogAction.role_update, after.id)

        emb = build_role_updated_embed(self.bot.settings, after.guild, before, after, actor)
        if emb:
            await logs.emit("channel_role", emb)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if not self._guild_ok(after.guild):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return

        if before.roles == after.roles:
            return

        actor = None
        if after.guild.me and after.guild.me.guild_permissions.view_audit_log:
            try:
                action = getattr(discord.AuditLogAction, "member_role_update", None)
                if action:
                    actor = await self._find_audit_actor(after.guild, action, after.id)
            except Exception:
                actor = None

        emb = build_member_roles_changed_embed(self.bot.settings, after.guild, before, after, actor)
        if emb:
            await logs.emit("channel_role", emb)

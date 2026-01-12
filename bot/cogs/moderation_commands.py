from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.utils.perms import is_staff
from bot.moderation.mod_service import ModerationService


async def _ephemeral(interaction: discord.Interaction, text: str):
    try:
        await interaction.response.send_message(text, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(text, ephemeral=True)


class ModerationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = ModerationService(bot, bot.settings, bot.db, getattr(bot, "forum_logs", None))

    def _need_guild(self, interaction: discord.Interaction):
        return interaction.guild and isinstance(interaction.user, discord.Member)

    @app_commands.command(name="timeout", description="Timeout (Auto-Dauer wenn du keine angibst).")
    @app_commands.describe(user="User", minutes="Minuten (leer = Auto)", reason="Grund")
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, minutes: int | None = None, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.moderate_members:
            return await _ephemeral(interaction, "Dir fehlt `Moderate Members`.")

        ok, err, used_minutes, strikes = await self.service.timeout(interaction.guild, interaction.user, user, minutes, reason)
        if not ok:
            return await _ephemeral(interaction, f"Timeout ging nicht: {err}")

        return await _ephemeral(interaction, f"Timeout gesetzt: **{used_minutes}min** (Strike **{strikes}**).")

    @app_commands.command(name="warn", description="Warnung vergeben.")
    @app_commands.describe(user="User", reason="Grund")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.moderate_members:
            return await _ephemeral(interaction, "Dir fehlt `Moderate Members`.")

        strikes = await self.service.warn(interaction.guild, interaction.user, user, reason)
        return await _ephemeral(interaction, f"Warnung vergeben. Strikes jetzt: **{strikes}**.")

    @app_commands.command(name="kick", description="User kicken.")
    @app_commands.describe(user="User", reason="Grund")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.kick_members:
            return await _ephemeral(interaction, "Dir fehlt `Kick Members`.")

        ok, err = await self.service.kick(interaction.guild, interaction.user, user, reason)
        if not ok:
            return await _ephemeral(interaction, f"Kick ging nicht: {err}")
        return await _ephemeral(interaction, f"{user.mention} wurde gekickt.")

    @app_commands.command(name="ban", description="User bannen.")
    @app_commands.describe(user="User", delete_days="Lösche Nachrichten der letzten X Tage (0-7)", reason="Grund")
    async def ban(self, interaction: discord.Interaction, user: discord.User, delete_days: int = 0, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.ban_members:
            return await _ephemeral(interaction, "Dir fehlt `Ban Members`.")

        ok, err, dd = await self.service.ban(interaction.guild, interaction.user, user, delete_days, reason)
        if not ok:
            return await _ephemeral(interaction, f"Ban ging nicht: {err}")
        return await _ephemeral(interaction, f"<@{user.id}> wurde gebannt. (delete_days={dd})")

    @app_commands.command(name="purge", description="Nachrichten löschen.")
    @app_commands.describe(amount="Wie viele (1-100)", user="Optional: nur dieser User", reason="Optional: interner Grund")
    async def purge(self, interaction: discord.Interaction, amount: int, user: discord.Member | None = None, reason: str | None = None):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_messages:
            return await _ephemeral(interaction, "Dir fehlt `Manage Messages`.")

        if not isinstance(interaction.channel, discord.TextChannel):
            return await _ephemeral(interaction, "Nur in normalen Text-Channels.")

        deleted, err = await self.service.purge(interaction.guild, interaction.user, interaction.channel, amount, user)
        if err:
            return await _ephemeral(interaction, f"Purge ging nicht: {err}")
        return await _ephemeral(interaction, f"Gelöscht: **{deleted}** Nachricht(en).")

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.perms import is_staff
from bot.modules.counting.services.counting_service import CountingService


async def _ephemeral(interaction: discord.Interaction, text: str):
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(text, ephemeral=True)
        else:
            await interaction.followup.send(text, ephemeral=True)
    except (discord.InteractionResponded, discord.NotFound, discord.HTTPException):
        try:
            await interaction.followup.send(text, ephemeral=True)
        except Exception:
            pass


class CountingCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "counting_service", None) or CountingService(bot, bot.settings, bot.db, bot.logger)

    def _need_guild(self, interaction: discord.Interaction) -> bool:
        return interaction.guild and isinstance(interaction.user, discord.Member)

    @app_commands.command(name="counting-reset", description="🔄 𑁉 Counting zurücksetzen")
    @app_commands.describe(full="Alles zurücksetzen (Highscore/Stats/Letzter Count)")
    async def counting_reset(self, interaction: discord.Interaction, full: bool = False):
        if not self._need_guild(interaction):
            return
        if not is_staff(self.bot.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")
        if not interaction.user.guild_permissions.manage_channels:
            return await _ephemeral(interaction, "Dir fehlt `Manage Channels`.")

        guild_id = int(interaction.guild.id)
        if not self.service._enabled(guild_id):
            return await _ephemeral(interaction, "Counting ist deaktiviert.")

        channel_id = self.service._channel_id(guild_id)
        if not channel_id:
            return await _ephemeral(interaction, "Counting-Channel ist nicht gesetzt.")

        state = await self.service.reset_state(channel_id, guild_id, full=full)
        self.service._schedule_channel_name_update(interaction.guild, channel_id, state)
        self.service._schedule_channel_topic_update(interaction.guild, channel_id, state)

        if full:
            return await _ephemeral(interaction, "Counting komplett zurückgesetzt.")
        return await _ephemeral(interaction, "Counting auf 1 zurückgesetzt.")

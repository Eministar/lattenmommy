from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.perms import is_staff
from bot.modules.ai.services.deepseek_service import DeepSeekService


class AICommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "deepseek_service", None) or DeepSeekService(bot, bot.settings, bot.logger)

    ai = app_commands.Group(name="ai", description="🤖 𑁉 AI-Tools")

    @ai.command(name="reset-limit", description="♻️ 𑁉 AI-Tageslimit zurücksetzen")
    @app_commands.describe(user="Optional: nur ein User")
    async def reset_limit(self, interaction: discord.Interaction, user: discord.User | None = None):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)

        if user:
            self.service.reset_daily_limit(interaction.guild.id, user.id)
            return await interaction.response.send_message(
                f"✅ Tageslimit für {user.mention} zurückgesetzt.",
                ephemeral=True,
            )

        count = self.service.reset_daily_limit(interaction.guild.id, None)
        return await interaction.response.send_message(
            f"✅ Tageslimit zurückgesetzt ({count} User).",
            ephemeral=True,
        )

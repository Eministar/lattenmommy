import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.parlament.services.parlament_service import ParliamentService


class ParliamentCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "parlament_service", None) or ParliamentService(bot, bot.settings, bot.db, bot.logger)

    parlament = app_commands.Group(name="parlament", description="🏛️ 𑁉 Parlament")
    start = app_commands.Group(name="start", description="Start", parent=parlament)
    stop = app_commands.Group(name="stop", description="Stop", parent=parlament)

    @start.command(name="vote", description="🗳️ 𑁉 Votum starten")
    async def start_vote(self, interaction: discord.Interaction):
        await self.service.start_vote(interaction)

    @stop.command(name="vote", description="🛑 𑁉 Votum stoppen")
    async def stop_vote(self, interaction: discord.Interaction):
        await self.service.stop_vote(interaction)

    @parlament.command(name="panel", description="📌 𑁉 Parlament-Panel aktualisieren")
    async def panel(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await self.service.update_panel(interaction.guild)
        await interaction.response.send_message("Panel aktualisiert.", ephemeral=True)

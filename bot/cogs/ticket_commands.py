import discord
from discord import app_commands
from discord.ext import commands

from bot.tickets.service import TicketService
from bot.utils.perms import is_staff


class TicketCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = TicketService(bot, bot.settings, bot.db, bot.logger)

    ticket = app_commands.Group(name="ticket", description="Ticket Tools")

    @ticket.command(name="beanspruchen", description="Ticket claimen/freigeben im aktuellen Thread")
    async def claim(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        await self.service.toggle_claim(interaction)

    @ticket.command(name="schliessen", description="Ticket schließen im aktuellen Thread")
    async def close(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        await interaction.response.send_message("Nutze bitte den Button „Ticket schließen“ im Embed.", ephemeral=True)

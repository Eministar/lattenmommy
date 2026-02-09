import discord
from discord.ext import commands
from bot.modules.tickets.services.ticket_service import TicketService


class TicketDMListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "ticket_service", None) or TicketService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is not None:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        app_service = getattr(self.bot, "application_service", None)
        if app_service and getattr(app_service, "is_dm_reserved", None):
            try:
                if app_service.is_dm_reserved(message.author.id):
                    return
            except Exception:
                pass
        await self.service.handle_dm(message)

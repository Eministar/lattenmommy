import discord
from discord.ext import commands
from bot.tickets.service import TicketService

class DMListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = TicketService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is not None:
            return
        if not isinstance(message.channel, discord.DMChannel):
            return
        await self.service.handle_dm(message)

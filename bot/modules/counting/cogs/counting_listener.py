import discord
from discord.ext import commands

from bot.modules.counting.services.counting_service import CountingService


class CountingListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "counting_service", None) or CountingService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self.service.handle_message(message)

from discord.ext import commands
import discord
from bot.modules.welcome.services.welcome_service import WelcomeService


class WelcomeListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "welcome_service", None) or WelcomeService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await self.service.handle_member_join(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await self.service.handle_member_leave(member)

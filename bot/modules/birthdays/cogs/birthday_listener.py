import discord
from discord.ext import commands
from bot.modules.birthdays.services.birthday_service import BirthdayService


class BirthdayListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "birthday_service", None) or BirthdayService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if not self.bot.settings.get_guild_bool(message.guild.id, "birthday.enabled", True):
            return
        await self.service.auto_react(message)

    @commands.Cog.listener("on_member_join")
    async def on_member_join(self, member: discord.Member):
        if not member.guild:
            return
        if not self.bot.settings.get_guild_bool(member.guild.id, "birthday.enabled", True):
            return
        await self.service.handle_member_join(member)

    @commands.Cog.listener("on_member_remove")
    async def on_member_remove(self, member: discord.Member):
        if not member.guild:
            return
        if not self.bot.settings.get_guild_bool(member.guild.id, "birthday.enabled", True):
            return
        await self.service.handle_member_remove(member)

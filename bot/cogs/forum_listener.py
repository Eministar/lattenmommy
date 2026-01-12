import discord
from discord.ext import commands
from bot.tickets.service import TicketService

class ForumListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = TicketService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        guild_id = self.bot.settings.get_int("bot.guild_id")
        if not guild_id or message.guild.id != guild_id:
            return
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.Thread):
            return
        forum_id = self.bot.settings.get_int("bot.forum_channel_id")
        parent = getattr(message.channel, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return
        await self.service.handle_staff_message(message)

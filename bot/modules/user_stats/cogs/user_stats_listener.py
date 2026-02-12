import discord
from discord.ext import commands
from bot.modules.user_stats.services.user_stats_service import UserStatsService


class UserStatsListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "user_stats_service", None) or UserStatsService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if not self.bot.settings.get_guild_bool(message.guild.id, "user_stats.enabled", True):
            return
        await self.service.on_message(message)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not self.bot.settings.get_guild_bool(after.guild.id, "user_stats.enabled", True):
            return
        await self.service.on_presence_update(before, after)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        enabled = self.bot.settings.get_guild_bool(after.guild.id, "user_stats.enabled", True)
        if not enabled:
            try:
                if before.premium_since != after.premium_since:
                    await self.service.sync_booster(after)
            except Exception:
                pass
            return
        await self.service.on_member_update(before, after)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        try:
            await self.service.sync_booster(member)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            await self.service.on_member_remove(member)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not self.bot.settings.get_guild_bool(member.guild.id, "user_stats.enabled", True):
            return
        await self.service.on_voice_state_update(member, before, after)

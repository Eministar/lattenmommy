import discord
from discord.ext import commands

from bot.modules.suggestions.services.suggestion_service import SuggestionService


class SuggestionForumListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "suggestion_service", None) or SuggestionService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self.service.handle_vote_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self.service.handle_vote_reaction(payload)


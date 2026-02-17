from __future__ import annotations

import discord
from discord.ext import commands

from bot.modules.automod.services.automod_service import AutoModService


class AutoModListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "automod_service", None) or AutoModService(bot, bot.settings, bot.db, bot.logger)

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        await self.service.handle_message(message)


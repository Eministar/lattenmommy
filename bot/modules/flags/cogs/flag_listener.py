from __future__ import annotations

import discord
from discord.ext import commands


class FlagListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "flag_quiz_service", None)

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if not self.service:
            return
        await self.service.handle_text_answer(message)


from __future__ import annotations

import discord
from discord.ext import commands


class PartyPanelListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        service = getattr(self.bot, "parlament_service", None)
        if not service:
            return
        try:
            await service.submit_party_program_from_message(message)
        except Exception:
            return

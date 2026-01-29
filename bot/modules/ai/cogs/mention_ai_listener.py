from __future__ import annotations

import discord
from discord.ext import commands

from bot.modules.ai.services.deepseek_service import DeepSeekService
from bot.modules.ai.formatting.ai_views import build_limit_view


class MentionAIListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "deepseek_service", None) or DeepSeekService(bot, bot.settings, bot.logger)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild:
            return
        if not message.content:
            return
        if message.author.bot:
            return
        if message.mention_everyone:
            return
        if not self.bot.user:
            return
        if self.bot.user not in message.mentions:
            return
        if not self.bot.settings.get_guild_bool(message.guild.id, "ai.enabled", True):
            return

        prompt = self.service.clean_prompt(self.bot.user.id, message.content)
        persona, prompt = self.service.extract_persona(prompt)
        if not prompt:
            return
        if not self.service.can_consume(message.guild.id, message.author.id):
            view = build_limit_view(self.bot.settings, message.guild, self.service.daily_limit())
            await message.reply(view=view, mention_author=False)
            return
        self.service.consume(message.guild.id, message.author.id)
        messages = self.service.build_messages(message.guild.id, message.author.id, prompt, persona=persona)

        async with message.channel.typing():
            reply, err = await self.service.generate_reply(message.guild.id, messages)

        if err:
            await message.reply("Konnte gerade nicht antworten.", mention_author=False)
            return
        if not reply:
            return

        self.service._set_session(message.guild.id, message.author.id, prompt, reply)
        await message.reply(reply, mention_author=False)

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.reminder_afk.services.reminder_afk_service import ReminderAfkService


class ReminderAfkCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "reminder_afk_service", None) or ReminderAfkService(bot, bot.settings, bot.db, bot.logger)

    reminder = app_commands.Group(name="reminder", description="⏰ 𑁉 Reminder-Tools")

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await self.service.handle_message_for_afk(message)

    @reminder.command(name="set", description="⏰ 𑁉 Reminder setzen")
    @app_commands.describe(time="z.B. 10m, 2h, 1d12h", text="Woran soll ich dich erinnern?")
    async def reminder_set(self, interaction: discord.Interaction, time: str, text: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, msg = await self.service.create_reminder(interaction.guild, interaction.user, int(interaction.channel_id), time, text)
        await interaction.response.send_message(msg, ephemeral=True)

    @reminder.command(name="list", description="📋 𑁉 Deine Reminder anzeigen")
    async def reminder_list(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        lines = await self.service.list_reminders(interaction.guild.id, interaction.user.id)
        if not lines:
            return await interaction.response.send_message("Du hast keine offenen Reminder.", ephemeral=True)
        await interaction.response.send_message("**Deine Reminder**\n" + "\n".join(lines[:20]), ephemeral=True)

    @reminder.command(name="remove", description="🗑️ 𑁉 Reminder löschen")
    @app_commands.describe(reminder_id="ID aus /reminder list")
    async def reminder_remove(self, interaction: discord.Interaction, reminder_id: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, msg = await self.service.remove_reminder(interaction.guild.id, interaction.user.id, int(reminder_id))
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="afk", description="💤 𑁉 AFK setzen")
    @app_commands.describe(reason="Optionaler AFK-Grund")
    async def afk(self, interaction: discord.Interaction, reason: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        msg = await self.service.set_afk(interaction.user, reason)
        await interaction.response.send_message(msg, ephemeral=True)

    @app_commands.command(name="unafk", description="✅ 𑁉 AFK manuell entfernen")
    async def unafk(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await self.service.clear_afk(interaction.guild.id, interaction.user.id)
        await interaction.response.send_message("AFK entfernt.", ephemeral=True)

    @commands.group(name="reminder", invoke_without_command=True)
    async def reminder_prefix(self, ctx: commands.Context):
        if not ctx.guild:
            return
        await ctx.reply("Nutze `!reminder set <zeit> <text>`, `!reminder list`, `!reminder remove <id>`.", mention_author=False)

    @reminder_prefix.command(name="set")
    async def reminder_prefix_set(self, ctx: commands.Context, time: str, *, text: str):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        ok, msg = await self.service.create_reminder(ctx.guild, ctx.author, int(ctx.channel.id), time, text)
        await ctx.reply(msg, mention_author=False)

    @reminder_prefix.command(name="list")
    async def reminder_prefix_list(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        lines = await self.service.list_reminders(ctx.guild.id, ctx.author.id)
        if not lines:
            return await ctx.reply("Du hast keine offenen Reminder.", mention_author=False)
        await ctx.reply("**Deine Reminder**\n" + "\n".join(lines[:20]), mention_author=False)

    @reminder_prefix.command(name="remove")
    async def reminder_prefix_remove(self, ctx: commands.Context, reminder_id: int):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        ok, msg = await self.service.remove_reminder(ctx.guild.id, ctx.author.id, int(reminder_id))
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="afk")
    async def afk_prefix(self, ctx: commands.Context, *, reason: str | None = None):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        msg = await self.service.set_afk(ctx.author, reason)
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="unafk")
    async def unafk_prefix(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        await self.service.clear_afk(ctx.guild.id, ctx.author.id)
        await ctx.reply("AFK entfernt.", mention_author=False)

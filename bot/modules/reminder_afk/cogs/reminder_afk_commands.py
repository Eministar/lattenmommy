from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
from discord.utils import format_dt

from bot.modules.reminder_afk.services.reminder_afk_service import ReminderAfkService


class AfkExtendButton(discord.ui.Button):
    def __init__(self, service: ReminderAfkService):
        super().__init__(
            label="AFK verlängern",
            style=discord.ButtonStyle.primary,
            emoji="⏳",
            custom_id="starry:afk:extend",
        )
        self.service = service

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, msg = await self.service.extend_afk_default(interaction.user)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        snap = await self.service.get_afk_snapshot(interaction.guild.id, interaction.user.id)
        if not snap:
            return await interaction.response.send_message("AFK nicht mehr aktiv.", ephemeral=True)
        view = build_afk_control_panel(self.service, interaction.guild, interaction.user, snap)
        await interaction.response.edit_message(view=view)


class AfkEndButton(discord.ui.Button):
    def __init__(self, service: ReminderAfkService):
        super().__init__(
            label="AFK beenden",
            style=discord.ButtonStyle.danger,
            emoji="✅",
            custom_id="starry:afk:end",
        )
        self.service = service

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, view = await self.service.clear_afk_with_summary(interaction.guild, interaction.user)
        if not ok:
            return await interaction.response.send_message("Du bist nicht AFK.", ephemeral=True)
        if view is not None:
            await interaction.response.edit_message(view=view)
        else:
            await interaction.response.send_message("AFK entfernt.", ephemeral=True)


def build_afk_control_panel(service: ReminderAfkService, guild: discord.Guild, user: discord.Member, snap: dict) -> discord.ui.LayoutView:
    set_at = str(snap.get("set_at") or "")
    until_at = str(snap.get("until_at") or "")
    reason = str(snap.get("reason") or "AFK")
    mentions = int(snap.get("mentions", 0) or 0)

    since = set_at
    try:
        since = format_dt(datetime.fromisoformat(set_at), style="R")
    except Exception:
        pass
    until = "manuell"
    if until_at:
        try:
            until = f"{format_dt(datetime.fromisoformat(until_at), style='R')}"
        except Exception:
            until = until_at

    lines = (
        f"┏`👤` - User: {user.mention}\n"
        f"┣`💬` - Grund: **{reason[:200]}**\n"
        f"┣`🕒` - Seit: {since}\n"
        f"┣`🔔` - Erwähnungen: **{mentions}**\n"
        f"┗`⏳` - Ende: {until}"
    )
    view = discord.ui.LayoutView(timeout=None)
    c = discord.ui.Container(accent_colour=service._color(guild))
    c.add_item(discord.ui.TextDisplay("**💤 𑁉 AFK PANEL**"))
    c.add_item(discord.ui.Separator())
    c.add_item(discord.ui.TextDisplay(lines))
    row = discord.ui.ActionRow()
    row.add_item(AfkExtendButton(service))
    row.add_item(AfkEndButton(service))
    c.add_item(discord.ui.Separator())
    c.add_item(row)
    view.add_item(c)
    return view


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

    @app_commands.command(name="afk", description="💤 𑁉 AFK setzen (mit optionaler Zeit)")
    @app_commands.describe(reason="Optionaler AFK-Grund", time="Optional: z.B. 30m, 2h, 1d")
    async def afk(self, interaction: discord.Interaction, reason: str | None = None, time: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, msg, view = await self.service.set_afk(interaction.user, reason, time)
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)
        snap = await self.service.get_afk_snapshot(interaction.guild.id, interaction.user.id)
        panel = build_afk_control_panel(self.service, interaction.guild, interaction.user, snap or {"reason": reason or "AFK", "set_at": "", "until_at": "", "mentions": 0})
        await interaction.response.send_message(ephemeral=True, view=panel)

    @app_commands.command(name="afk-status", description="📊 𑁉 Zeigt deinen aktuellen AFK-Status")
    async def afk_status(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        row = await self.bot.db.get_afk_status(interaction.guild.id, interaction.user.id)
        if not row:
            return await interaction.response.send_message("Du bist aktuell nicht AFK.", ephemeral=True)
        reason = str(row[2] or "AFK")
        set_at = str(row[3] or "")
        until_at = str(row[4] or "")
        events = await self.bot.db.list_afk_mention_events(interaction.guild.id, interaction.user.id, limit=1000)
        view = build_afk_control_panel(
            self.service,
            interaction.guild,
            interaction.user,
            {"reason": reason, "set_at": set_at, "until_at": until_at, "mentions": len(events)},
        )
        await interaction.response.send_message(ephemeral=True, view=view)

    @app_commands.command(name="unafk", description="✅ 𑁉 AFK manuell entfernen + Zusammenfassung")
    async def unafk(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, view = await self.service.clear_afk_with_summary(interaction.guild, interaction.user)
        if not ok:
            return await interaction.response.send_message("Du bist nicht AFK.", ephemeral=True)
        if view is not None:
            await interaction.response.send_message(ephemeral=True, view=view)
        else:
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
    async def afk_prefix(self, ctx: commands.Context, *, payload: str | None = None):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        text = str(payload or "").strip()
        time = None
        reason = None
        if text:
            parts = text.split(" ", 1)
            if self.service._parse_duration(parts[0]):
                time = parts[0]
                reason = parts[1] if len(parts) > 1 else None
            else:
                reason = text
        ok, msg, _ = await self.service.set_afk(ctx.author, reason, time)
        await ctx.reply(msg, mention_author=False)

    @commands.command(name="afkstatus")
    async def afkstatus_prefix(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        row = await self.bot.db.get_afk_status(ctx.guild.id, ctx.author.id)
        if not row:
            return await ctx.reply("Du bist aktuell nicht AFK.", mention_author=False)
        reason = str(row[2] or "AFK")
        set_at = str(row[3] or "")
        until_at = str(row[4] or "")
        events = await self.bot.db.list_afk_mention_events(ctx.guild.id, ctx.author.id, limit=1000)
        await ctx.reply(
            f"AFK aktiv | Grund: **{reason}** | Seit: `{set_at or '—'}` | Bis: `{until_at or '—'}` | Erwähnungen: **{len(events)}**",
            mention_author=False,
        )

    @commands.command(name="unafk")
    async def unafk_prefix(self, ctx: commands.Context):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return
        ok, _ = await self.service.clear_afk_with_summary(ctx.guild, ctx.author)
        if not ok:
            return await ctx.reply("Du bist nicht AFK.", mention_author=False)
        await ctx.reply("AFK entfernt. Willkommen zurück.", mention_author=False)

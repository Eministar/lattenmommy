from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.perms import is_staff
from bot.modules.flags.formatting.flag_embeds import build_leaderboard_embed, build_streaks_embed


class FlagCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "flag_quiz_service", None)

    flag = app_commands.Group(name="flag", description="🏴 𑁉 Flaggenquiz")

    @flag.command(name="setup", description="⚙️ 𑁉 Flaggenquiz-Kanal setzen + Dashboard senden")
    @app_commands.describe(channel="Quiz-Kanal (optional)")
    async def setup(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True, delete_after=30)
        if not self.service:
            return await interaction.response.send_message("Flag-Service nicht verfügbar.", ephemeral=True, delete_after=30)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message("Bitte Textkanal nutzen.", ephemeral=True, delete_after=30)
        await interaction.response.defer(ephemeral=True)
        await self.service.setup_channel(interaction.guild, target)
        await interaction.edit_original_response(content=f"Flaggenquiz ist jetzt in {target.mention} aktiv.")

    @flag.command(name="panel", description="♻️ 𑁉 Flaggen-Panel aktualisieren/wiederverwenden")
    @app_commands.describe(channel="Optional anderer Kanal")
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True, delete_after=30)
        if not self.service:
            return await interaction.response.send_message("Flag-Service nicht verfügbar.", ephemeral=True, delete_after=30)
        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message("Bitte Textkanal nutzen.", ephemeral=True, delete_after=30)
        await interaction.response.defer(ephemeral=True)
        await self.service.ensure_dashboard(interaction.guild, target)
        await interaction.edit_original_response(content=f"Flaggen-Panel in {target.mention} aktualisiert.")

    @flag.command(name="start", description="🎯 𑁉 Neues Flaggenrätsel starten")
    @app_commands.describe(mode="normal / easy")
    @app_commands.choices(mode=[
        app_commands.Choice(name="normal", value="normal"),
        app_commands.Choice(name="easy", value="easy"),
    ])
    async def start(self, interaction: discord.Interaction, mode: app_commands.Choice[str] | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        if not self.service:
            return await interaction.response.send_message("Flag-Service nicht verfügbar.", ephemeral=True, delete_after=30)
        mode_key = str(mode.value) if mode else "normal"
        ok, msg = await self.service.start_round(interaction.guild, interaction.channel, interaction.user, mode_key)
        await interaction.response.send_message(msg, ephemeral=True, delete_after=30)

    @flag.command(name="daily", description="📆 𑁉 Daily-Flagge (1x pro Tag)")
    async def daily(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        if not self.service:
            return await interaction.response.send_message("Flag-Service nicht verfügbar.", ephemeral=True, delete_after=30)
        ok, msg = await self.service.start_round(interaction.guild, interaction.channel, interaction.user, "daily")
        await interaction.response.send_message(msg, ephemeral=True, delete_after=30)

    @flag.command(name="leaderboard", description="🏆 𑁉 Top-Spieler")
    async def leaderboard(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        rows = await self.bot.db.list_flag_players_top_points(interaction.guild.id, limit=10)
        emb = build_leaderboard_embed(self.bot.settings, interaction.guild, rows)
        await interaction.response.send_message(embed=emb, ephemeral=True, delete_after=30)

    @flag.command(name="streaks", description="🔥 𑁉 Top-Streaks")
    async def streaks(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        rows = await self.bot.db.list_flag_players_top_streak(interaction.guild.id, limit=10)
        emb = build_streaks_embed(self.bot.settings, interaction.guild, rows)
        await interaction.response.send_message(embed=emb, ephemeral=True, delete_after=30)

    @flag.command(name="stats", description="📊 𑁉 Spieler-Stats")
    @app_commands.describe(user="Optional anderer User")
    async def stats(self, interaction: discord.Interaction, user: discord.Member | None = None):
        if not interaction.guild or not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        target = user or interaction.user
        stats = await self.service.stats_for(interaction.guild.id, int(target.id))
        text = (
            f"**Stats von {target.display_name}**\n"
            f"Punkte: **{int(stats['total_points'])}**\n"
            f"Richtig: **{int(stats['correct'])}** • Falsch: **{int(stats['wrong'])}**\n"
            f"Streak: **{int(stats['current_streak'])}** (Best: {int(stats['best_streak'])})"
        )
        await interaction.response.send_message(text, ephemeral=True, delete_after=30)

    @flag.command(name="info", description="🚩 𑁉 Infos zu einer Flagge")
    @app_commands.describe(land="Land oder ISO-Code (z.B. DE)")
    async def info(self, interaction: discord.Interaction, land: str):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        code, name, fs = await self.service.flag_info(interaction.guild.id, land)
        if not code:
            return await interaction.response.send_message("Land nicht erkannt.", ephemeral=True, delete_after=30)
        emb = discord.Embed(
            title=f"🚩 𑁉 {name} ({code})",
            description=(
                f"Gestellt: **{int(fs['asked'])}**\n"
                f"Richtig: **{int(fs['correct'])}** • Falsch: **{int(fs['wrong'])}**"
            ),
            color=0xB16B91,
        )
        emb.set_image(url=self.service._flag_url_for(code))
        await interaction.response.send_message(embed=emb, ephemeral=True, delete_after=30)

    @flag.command(name="topflags", description="📈 𑁉 Meistgefragte Flaggen")
    @app_commands.describe(limit="Anzahl (max 20)")
    async def topflags(self, interaction: discord.Interaction, limit: int = 10):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True, delete_after=30)
        n = max(1, min(20, int(limit)))
        rows = await self.bot.db.list_flag_stats_top_asked(interaction.guild.id, limit=n)
        if not rows:
            return await interaction.response.send_message("Noch keine Flaggen-Stats.", ephemeral=True, delete_after=30)
        lines = []
        for i, row in enumerate(rows, 1):
            code = str(row[0])
            asked = int(row[1] or 0)
            corr = int(row[2] or 0)
            wrong = int(row[3] or 0)
            total = max(1, corr + wrong)
            pct = round((corr / total) * 100)
            lines.append(f"#{i} **{code}** - gefragt **{asked}x** • ✅ {corr} • ❌ {wrong} • {pct}%")
        await interaction.response.send_message("**📈 Top Flaggen**\n" + "\n".join(lines), ephemeral=True, delete_after=30)

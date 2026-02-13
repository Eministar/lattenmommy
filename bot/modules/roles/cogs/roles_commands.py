import discord
from discord import app_commands
from discord.ext import commands
from bot.core.perms import is_staff
import asyncio
from bot.modules.roles.views.roles_info_panel import RolesInfoPanelView


class RolesCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    roles = app_commands.Group(name="roles", description="🧩 𑁉 Rollen-Tools")
    roll = app_commands.Group(name="roll", description="🧩 𑁉 Rollen-Bereich")
    roll_info = app_commands.Group(name="roll-info", description="ℹ️ 𑁉 Rollen-Infos", parent=roll)

    @roles.command(name="sync", description="🔄 𑁉 Auto-Rollen syncen")
    async def sync(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await interaction.response.send_message("Rollen-Sync läuft…", ephemeral=True)
        try:
            if getattr(self.bot, "user_stats_service", None):
                await self.bot.user_stats_service.ensure_roles(interaction.guild)
            if getattr(self.bot, "birthday_service", None):
                await self.bot.birthday_service.ensure_roles(interaction.guild)
            await interaction.followup.send("Rollen-Sync abgeschlossen.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Rollen-Sync fehlgeschlagen: `{type(e).__name__}`", ephemeral=True)

    @roles.command(name="rescan", description="🧭 𑁉 Erfolge & Rollen neu prüfen")
    async def rescan(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        await interaction.response.send_message("Rescan läuft… (kann etwas dauern)", ephemeral=True)
        try:
            if not getattr(self.bot, "user_stats_service", None):
                return await interaction.followup.send("User-Stats-Service fehlt.", ephemeral=True)
            result = await self.bot.user_stats_service.rescan_guild(
                interaction.guild,
                birthday_service=getattr(self.bot, "birthday_service", None),
            )
            await interaction.followup.send(
                f"Rescan fertig. Users: **{result['scanned']}** | "
                f"Erfolge neu: **{result['achievements_new']}** | "
                f"Birthday neu: **{result['birthday_new']}**",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(f"Rescan fehlgeschlagen: `{type(e).__name__}`", ephemeral=True)

    @roles.command(name="mass-add", description="🧩 𑁉 Rolle an alle vergeben")
    @app_commands.describe(role="Rolle, die alle bekommen sollen")
    async def mass_add(self, interaction: discord.Interaction, role: discord.Role):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        await interaction.response.send_message("Mass-Role läuft…", ephemeral=True)
        added = 0
        failed = 0
        for member in interaction.guild.members:
            if member.bot:
                continue
            if role in member.roles:
                continue
            try:
                await member.add_roles(role, reason="Mass role add")
                added += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.2)
        await interaction.followup.send(
            f"Mass-Role fertig. Hinzugefügt: **{added}**, Fehler: **{failed}**",
            ephemeral=True,
        )

    @roll_info.command(name="panel-senden", description="ℹ️ 𑁉 Rollen-Info Panel senden")
    @app_commands.describe(channel="Zielkanal (optional)")
    async def roll_info_panel_send(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        target = channel or interaction.channel
        if not isinstance(target, discord.abc.Messageable):
            return await interaction.response.send_message("Zielkanal ungültig.", ephemeral=True)
        await target.send(view=RolesInfoPanelView(self.bot.settings, interaction.guild))
        await interaction.response.send_message("Rollen-Info Panel gesendet.", ephemeral=True)

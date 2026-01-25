import discord
from discord import app_commands
from discord.ext import commands
from bot.core.perms import is_staff


class RolesCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    roles = app_commands.Group(name="roles", description="🧩 𑁉 Rollen-Tools")

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

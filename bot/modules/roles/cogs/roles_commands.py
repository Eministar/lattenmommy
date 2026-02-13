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

    @staticmethod
    def _to_role_ids(raw) -> list[int]:
        if isinstance(raw, (tuple, set)):
            raw = list(raw)
        elif isinstance(raw, str):
            raw = [p.strip() for p in raw.split(",") if p.strip()]
        elif not isinstance(raw, list):
            return []
        out: list[int] = []
        for item in raw:
            try:
                if isinstance(item, dict):
                    out.append(int(item.get("role_id", 0) or 0))
                else:
                    out.append(int(item))
            except Exception:
                continue
        return [int(v) for v in out if int(v) > 0]

    @staticmethod
    def _raw_from_base(settings, dotted: str):
        node = getattr(settings, "_base", {}) or {}
        for part in str(dotted).split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node

    def _resolve_role_info_ids(self, guild_id: int, category: str) -> tuple[str, list[int]]:
        settings = self.bot.settings
        key_new = f"role-info.{category}_role_ids"
        key_old = f"roles.{category}_role_ids"
        keys = [key_new, key_old]
        for key in keys:
            raw = settings.get_guild(guild_id, key, None)
            ids = self._to_role_ids(raw)
            if ids:
                return f"guild:{key}", ids
            raw = settings.get(key, None)
            ids = self._to_role_ids(raw)
            if ids:
                return f"global:{key}", ids
            raw = self._raw_from_base(settings, key)
            ids = self._to_role_ids(raw)
            if ids:
                return f"base:{key}", ids
        return "none", []

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

    @roll_info.command(name="debug", description="🧪 𑁉 Zeigt geladene Role-Info IDs + Treffer")
    async def roll_info_debug(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)

        guild = interaction.guild
        team_source, team_ids = self._resolve_role_info_ids(guild.id, "team")
        special_source, special_ids = self._resolve_role_info_ids(guild.id, "special")

        def _block(name: str, source: str, ids: list[int]) -> str:
            found = [rid for rid in ids if guild.get_role(int(rid))]
            missing = [rid for rid in ids if not guild.get_role(int(rid))]
            lines = [
                f"`Quelle`: `{source}`",
                f"`IDs`: **{len(ids)}** | `gefunden`: **{len(found)}** | `fehlend`: **{len(missing)}**",
            ]
            if found:
                lines.append("`Gefunden`: " + ", ".join(f"<@&{rid}>" for rid in found[:10]))
            if missing:
                lines.append("`Fehlend`: " + ", ".join(f"`{rid}`" for rid in missing[:10]))
            if len(found) > 10:
                lines.append(f"`…` +{len(found) - 10} weitere gefundene")
            if len(missing) > 10:
                lines.append(f"`…` +{len(missing) - 10} weitere fehlende")
            return f"**{name}**\n" + "\n".join(lines)

        text = (
            f"**🧪 𑁉 ROLE-INFO DEBUG**\n"
            f"`Guild`: `{guild.name}` (`{guild.id}`)\n\n"
            f"{_block('🛡️ Team', team_source, team_ids)}\n\n"
            f"{_block('✨ Sonder', special_source, special_ids)}"
        )
        await interaction.response.send_message(text, ephemeral=True)

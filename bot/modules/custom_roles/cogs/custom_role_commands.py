from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.core.perms import is_staff
from bot.modules.custom_roles.services.custom_role_service import CustomRoleService


class CustomRoleCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "custom_role_service", None) or CustomRoleService(bot, bot.settings, bot.db, bot.logger)

    custom_role = app_commands.Group(name="custom-role", description="🎨 𑁉 Custom-Rollen")

    def _need_ctx(self, ctx: commands.Context) -> bool:
        return bool(ctx.guild and isinstance(ctx.author, discord.Member))

    async def _ctx_reply(self, ctx: commands.Context, text: str):
        try:
            await ctx.reply(text, mention_author=False)
        except Exception:
            try:
                await ctx.send(text)
            except Exception:
                pass

    def _is_admin(self, member: discord.Member) -> bool:
        if is_staff(self.bot.settings, member):
            return True
        return bool(member.guild_permissions.manage_roles)

    def _admin_max_emojis(self, guild_id: int) -> int:
        try:
            val = int(self.bot.settings.get_guild(guild_id, "custom_roles.admin_max_emojis", None) or 0)
            if val <= 0:
                val = int(self.bot.settings.get_guild(guild_id, "roles.custom_role.admin_max_emojis", 20) or 20)
        except Exception:
            val = 20
        return max(1, min(20, val))

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if not self.service.enabled(message.guild.id):
            return
        if message.mention_everyone or message.role_mentions:
            return
        mentions = [m for m in (message.mentions or []) if isinstance(m, discord.Member) and not m.bot and m.id != message.author.id]
        if not mentions:
            return
        emojis, _ = await self.service.read_reactions(message.guild.id, message.author.id)
        if not emojis:
            return
        for e in emojis:
            try:
                await message.add_reaction(e)
            except Exception:
                continue

    @custom_role.command(name="create", description="🎨 𑁉 Eigene Rolle erstellen/aktualisieren")
    @app_commands.describe(
        name="Rollenname",
        color_hex="Farbe in HEX, z.B. #FF77AA",
        emojis="Reaktions-Emojis, getrennt mit Leerzeichen oder Komma",
        icon="Optionales Role-Icon (Bild, max. 256KB)",
    )
    async def custom_role_create(
        self,
        interaction: discord.Interaction,
        name: str,
        color_hex: str | None = None,
        emojis: str | None = None,
        icon: discord.Attachment | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self.service.enabled(interaction.guild.id):
            return await interaction.response.send_message("Custom-Rollen sind deaktiviert.", ephemeral=True)

        perks = await self.service.perks(interaction.user)
        reaction_emojis = self.service.parse_emojis(emojis) or self.service.default_reactions(interaction.guild.id)
        reaction_emojis = reaction_emojis[: int(perks["max_emojis"])]
        if not reaction_emojis:
            return await interaction.response.send_message("Mindestens ein Emoji ist nötig.", ephemeral=True)

        icon_data, icon_err = await self.service.load_icon_bytes(icon)
        if icon_err:
            return await interaction.response.send_message(icon_err, ephemeral=True)

        ok, text = await self.service.upsert_member_role(
            interaction.user,
            str(name),
            self.service.parse_color(color_hex),
            reaction_emojis,
            int(perks["max_emojis"]),
            icon_data,
            bool(perks["can_icon"]),
        )
        if not ok:
            return await interaction.response.send_message(text, ephemeral=True)
        await interaction.response.send_message(
            f"{text}\nLevel: **{perks['level']}** | Booster: **{'Ja' if perks['is_booster'] else 'Nein'}**",
            ephemeral=True,
        )

    @custom_role.command(name="emojis", description="😄 𑁉 Reaktions-Emojis für deine Pings setzen")
    @app_commands.describe(emojis="Reaktions-Emojis, getrennt mit Leerzeichen oder Komma")
    async def custom_role_emojis(self, interaction: discord.Interaction, emojis: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self.service.enabled(interaction.guild.id):
            return await interaction.response.send_message("Custom-Rollen sind deaktiviert.", ephemeral=True)
        perks = await self.service.perks(interaction.user)
        reaction_emojis = self.service.parse_emojis(emojis)[: int(perks["max_emojis"])]
        ok, text = await self.service.set_member_emojis(interaction.user, reaction_emojis, int(perks["max_emojis"]))
        await interaction.response.send_message(text, ephemeral=True)

    @custom_role.command(name="remove", description="🗑️ 𑁉 Eigene Custom-Rolle entfernen")
    async def custom_role_remove(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, text = await self.service.remove_member_role(interaction.user)
        await interaction.response.send_message(text, ephemeral=True)

    @custom_role.command(name="info", description="📊 𑁉 Deine Custom-Rollen-Perks anzeigen")
    async def custom_role_info(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        perks = await self.service.perks(interaction.user)
        emojis, cap = await self.service.read_reactions(interaction.guild.id, interaction.user.id)
        row = await self.bot.db.get_custom_role(interaction.guild.id, interaction.user.id)
        role_text = "—"
        if row:
            try:
                rid = int(row[2] or 0)
                role = interaction.guild.get_role(rid)
                role_text = role.mention if role else f"`{rid}`"
            except Exception:
                pass
        await interaction.response.send_message(
            f"**🎨 𑁉 CUSTOM-ROLE INFO**\n"
            f"Rolle: {role_text}\n"
            f"Level: **{perks['level']}** | Booster: **{'Ja' if perks['is_booster'] else 'Nein'}**\n"
            f"Emoji-Limit jetzt: **{perks['max_emojis']}**\n"
            f"Gespeicherte Emojis: **{len(emojis)}/{cap}**\n"
            f"Emojis: {' '.join(emojis) if emojis else '—'}",
            ephemeral=True,
        )

    @custom_role.command(name="upload-emoji", description="🧩 𑁉 Eigenes Emoji hochladen und nutzen")
    @app_commands.describe(name="Emoji-Name", image="Emoji-Bild (PNG/JPG/GIF)")
    async def custom_role_upload_emoji(self, interaction: discord.Interaction, name: str, image: discord.Attachment):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self.service.enabled(interaction.guild.id):
            return await interaction.response.send_message("Custom-Rollen sind deaktiviert.", ephemeral=True)
        perks = await self.service.perks(interaction.user)
        if not perks.get("can_upload_emoji", False):
            return await interaction.response.send_message("Emoji-Upload erst ab freigeschaltetem Level oder als Booster.", ephemeral=True)
        data, err = await self.service.load_icon_bytes(image)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        ok, msg, token = await self.service.upload_guild_emoji(interaction.guild, interaction.user, name, data or b"")
        if not ok:
            return await interaction.response.send_message(msg, ephemeral=True)

        row = await self.bot.db.get_custom_role(interaction.guild.id, interaction.user.id)
        if row and token:
            emojis, cap = await self.service.read_reactions(interaction.guild.id, interaction.user.id)
            if token not in emojis and len(emojis) < cap:
                emojis.append(token)
                await self.service.set_member_emojis(interaction.user, emojis, cap)
                msg += f"\nAls Ping-Reaction hinzugefügt ({len(emojis)}/{cap})."
        await interaction.response.send_message(msg, ephemeral=True)

    @custom_role.command(name="admin-grant", description="🛠️ 𑁉 Admin: Free-Custom-Rolle für User vergeben")
    @app_commands.describe(
        user="Zieluser",
        name="Rollenname",
        color_hex="HEX-Farbe, z.B. #FF77AA",
        emojis="Reaktions-Emojis",
        icon="Optionales Role-Icon",
    )
    async def custom_role_admin_grant(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        name: str,
        color_hex: str | None = None,
        emojis: str | None = None,
        icon: discord.Attachment | None = None,
    ):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        if not self.service.enabled(interaction.guild.id):
            return await interaction.response.send_message("Custom-Rollen sind deaktiviert.", ephemeral=True)

        max_emojis = self._admin_max_emojis(interaction.guild.id)
        reaction_emojis = self.service.parse_emojis(emojis) or self.service.default_reactions(interaction.guild.id)
        reaction_emojis = reaction_emojis[:max_emojis]
        if not reaction_emojis:
            return await interaction.response.send_message("Mindestens ein Emoji ist nötig.", ephemeral=True)

        icon_data, icon_err = await self.service.load_icon_bytes(icon)
        if icon_err:
            return await interaction.response.send_message(icon_err, ephemeral=True)

        ok, text = await self.service.upsert_member_role(
            user,
            str(name),
            self.service.parse_color(color_hex),
            reaction_emojis,
            max_emojis,
            icon_data,
            True,
        )
        await interaction.response.send_message(text, ephemeral=True)

    @custom_role.command(name="admin-emojis", description="🛠️ 𑁉 Admin: Ping-Emojis für User setzen")
    @app_commands.describe(user="Zieluser", emojis="Reaktions-Emojis")
    async def custom_role_admin_emojis(self, interaction: discord.Interaction, user: discord.Member, emojis: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        max_emojis = self._admin_max_emojis(interaction.guild.id)
        reaction_emojis = self.service.parse_emojis(emojis)[:max_emojis]
        ok, text = await self.service.set_member_emojis(user, reaction_emojis, max_emojis)
        await interaction.response.send_message(text, ephemeral=True)

    @custom_role.command(name="admin-clear-emojis", description="🛠️ 𑁉 Admin: Ping-Emojis bei User entfernen")
    @app_commands.describe(user="Zieluser")
    async def custom_role_admin_clear_emojis(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        row = await self.bot.db.get_custom_role(interaction.guild.id, user.id)
        if not row:
            return await interaction.response.send_message("User hat keine gespeicherte Custom-Rolle.", ephemeral=True)
        await self.bot.db.upsert_custom_role(
            interaction.guild.id,
            user.id,
            int(row[2]),
            str(row[3]),
            "[]",
            int(row[5] or 1),
        )
        await interaction.response.send_message("Ping-Emojis wurden entfernt.", ephemeral=True)

    @custom_role.command(name="admin-revoke", description="🛠️ 𑁉 Admin: Custom-Rolle bei User entfernen")
    @app_commands.describe(user="Zieluser")
    async def custom_role_admin_revoke(self, interaction: discord.Interaction, user: discord.Member):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self._is_admin(interaction.user):
            return await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        ok, text = await self.service.remove_member_role(user)
        await interaction.response.send_message(text, ephemeral=True)

    @commands.group(name="customrole", invoke_without_command=True)
    async def customrole_prefix(self, ctx: commands.Context):
        if not self._need_ctx(ctx):
            return
        await self._ctx_reply(
            ctx,
            "Verfügbar: `!customrole create <name> [#hex] [emojis]`, `!customrole emojis <emojis>`, `!customrole upload-emoji <name>`, `!customrole info`, `!customrole remove`, `!customrole admin-*`",
        )

    @customrole_prefix.command(name="create")
    async def customrole_prefix_create(self, ctx: commands.Context, name: str, color_hex: str | None = None, *, emojis: str | None = None):
        if not self._need_ctx(ctx):
            return
        member = ctx.author
        if not isinstance(member, discord.Member):
            return
        if not self.service.enabled(ctx.guild.id):
            return await self._ctx_reply(ctx, "Custom-Rollen sind deaktiviert.")
        perks = await self.service.perks(member)
        reaction_emojis = self.service.parse_emojis(emojis) or self.service.default_reactions(ctx.guild.id)
        reaction_emojis = reaction_emojis[: int(perks["max_emojis"])]
        attach = ctx.message.attachments[0] if ctx.message.attachments else None
        icon_data, icon_err = await self.service.load_icon_bytes(attach)
        if icon_err:
            return await self._ctx_reply(ctx, icon_err)
        ok, text = await self.service.upsert_member_role(
            member,
            str(name),
            self.service.parse_color(color_hex),
            reaction_emojis,
            int(perks["max_emojis"]),
            icon_data,
            bool(perks["can_icon"]),
        )
        await self._ctx_reply(ctx, text)

    @customrole_prefix.command(name="emojis")
    async def customrole_prefix_emojis(self, ctx: commands.Context, *, emojis: str):
        if not self._need_ctx(ctx):
            return
        member = ctx.author
        if not isinstance(member, discord.Member):
            return
        perks = await self.service.perks(member)
        reaction_emojis = self.service.parse_emojis(emojis)[: int(perks["max_emojis"])]
        ok, text = await self.service.set_member_emojis(member, reaction_emojis, int(perks["max_emojis"]))
        await self._ctx_reply(ctx, text)

    @customrole_prefix.command(name="remove")
    async def customrole_prefix_remove(self, ctx: commands.Context):
        if not self._need_ctx(ctx):
            return
        if not isinstance(ctx.author, discord.Member):
            return
        ok, text = await self.service.remove_member_role(ctx.author)
        await self._ctx_reply(ctx, text)

    @customrole_prefix.command(name="info")
    async def customrole_prefix_info(self, ctx: commands.Context):
        if not self._need_ctx(ctx):
            return
        member = ctx.author
        if not isinstance(member, discord.Member):
            return
        perks = await self.service.perks(member)
        emojis, cap = await self.service.read_reactions(ctx.guild.id, member.id)
        row = await self.bot.db.get_custom_role(ctx.guild.id, member.id)
        role_text = "—"
        if row:
            try:
                rid = int(row[2] or 0)
                role = ctx.guild.get_role(rid)
                role_text = role.mention if role else f"`{rid}`"
            except Exception:
                pass
        await self._ctx_reply(
            ctx,
            f"Custom-Rolle: {role_text} | Level: {perks['level']} | Booster: {'Ja' if perks['is_booster'] else 'Nein'} | "
            f"Emoji-Limit: {perks['max_emojis']} | Emojis: {' '.join(emojis) if emojis else '—'} ({len(emojis)}/{cap})",
        )

    @customrole_prefix.command(name="upload-emoji")
    async def customrole_prefix_upload_emoji(self, ctx: commands.Context, name: str):
        if not self._need_ctx(ctx):
            return
        if not isinstance(ctx.author, discord.Member):
            return
        if not self.service.enabled(ctx.guild.id):
            return await self._ctx_reply(ctx, "Custom-Rollen sind deaktiviert.")
        perks = await self.service.perks(ctx.author)
        if not perks.get("can_upload_emoji", False):
            return await self._ctx_reply(ctx, "Emoji-Upload erst ab freigeschaltetem Level oder als Booster.")
        if not ctx.message.attachments:
            return await self._ctx_reply(ctx, "Bitte ein Bild als Attachment mitschicken.")
        data, err = await self.service.load_icon_bytes(ctx.message.attachments[0])
        if err:
            return await self._ctx_reply(ctx, err)
        ok, msg, token = await self.service.upload_guild_emoji(ctx.guild, ctx.author, name, data or b"")
        if not ok:
            return await self._ctx_reply(ctx, msg)
        row = await self.bot.db.get_custom_role(ctx.guild.id, ctx.author.id)
        if row and token:
            emojis, cap = await self.service.read_reactions(ctx.guild.id, ctx.author.id)
            if token not in emojis and len(emojis) < cap:
                emojis.append(token)
                await self.service.set_member_emojis(ctx.author, emojis, cap)
                msg += f" | Als Ping-Reaction hinzugefügt ({len(emojis)}/{cap})."
        await self._ctx_reply(ctx, msg)

    @customrole_prefix.command(name="admin-grant")
    async def customrole_prefix_admin_grant(
        self,
        ctx: commands.Context,
        user: discord.Member,
        name: str,
        color_hex: str | None = None,
        *,
        emojis: str | None = None,
    ):
        if not self._need_ctx(ctx):
            return
        if not isinstance(ctx.author, discord.Member) or not self._is_admin(ctx.author):
            return await self._ctx_reply(ctx, "Keine Berechtigung.")
        if not self.service.enabled(ctx.guild.id):
            return await self._ctx_reply(ctx, "Custom-Rollen sind deaktiviert.")
        max_emojis = self._admin_max_emojis(ctx.guild.id)
        reaction_emojis = self.service.parse_emojis(emojis) or self.service.default_reactions(ctx.guild.id)
        reaction_emojis = reaction_emojis[:max_emojis]
        attach = ctx.message.attachments[0] if ctx.message.attachments else None
        icon_data, icon_err = await self.service.load_icon_bytes(attach)
        if icon_err:
            return await self._ctx_reply(ctx, icon_err)
        ok, text = await self.service.upsert_member_role(
            user,
            str(name),
            self.service.parse_color(color_hex),
            reaction_emojis,
            max_emojis,
            icon_data,
            True,
        )
        await self._ctx_reply(ctx, text)

    @customrole_prefix.command(name="admin-emojis")
    async def customrole_prefix_admin_emojis(self, ctx: commands.Context, user: discord.Member, *, emojis: str):
        if not self._need_ctx(ctx):
            return
        if not isinstance(ctx.author, discord.Member) or not self._is_admin(ctx.author):
            return await self._ctx_reply(ctx, "Keine Berechtigung.")
        max_emojis = self._admin_max_emojis(ctx.guild.id)
        reaction_emojis = self.service.parse_emojis(emojis)[:max_emojis]
        ok, text = await self.service.set_member_emojis(user, reaction_emojis, max_emojis)
        await self._ctx_reply(ctx, text)

    @customrole_prefix.command(name="admin-clear-emojis")
    async def customrole_prefix_admin_clear_emojis(self, ctx: commands.Context, user: discord.Member):
        if not self._need_ctx(ctx):
            return
        if not isinstance(ctx.author, discord.Member) or not self._is_admin(ctx.author):
            return await self._ctx_reply(ctx, "Keine Berechtigung.")
        row = await self.bot.db.get_custom_role(ctx.guild.id, user.id)
        if not row:
            return await self._ctx_reply(ctx, "User hat keine gespeicherte Custom-Rolle.")
        await self.bot.db.upsert_custom_role(
            ctx.guild.id,
            user.id,
            int(row[2]),
            str(row[3]),
            "[]",
            int(row[5] or 1),
        )
        await self._ctx_reply(ctx, "Ping-Emojis wurden entfernt.")

    @customrole_prefix.command(name="admin-revoke")
    async def customrole_prefix_admin_revoke(self, ctx: commands.Context, user: discord.Member):
        if not self._need_ctx(ctx):
            return
        if not isinstance(ctx.author, discord.Member) or not self._is_admin(ctx.author):
            return await self._ctx_reply(ctx, "Keine Berechtigung.")
        ok, text = await self.service.remove_member_role(user)
        await self._ctx_reply(ctx, text)

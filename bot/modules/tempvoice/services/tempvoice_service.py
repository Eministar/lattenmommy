import discord
from datetime import datetime, timezone
from bot.core.perms import is_staff
from bot.modules.tempvoice.views.tempvoice_panel import TempVoicePanelView
from bot.modules.tempvoice.formatting.tempvoice_embeds import (
    build_tempvoice_panel_container,
    build_tempvoice_invite_embed,
)
from bot.utils.emojis import em


def _normalize_room(row):
    if not row:
        return None
    try:
        return {
            "guild_id": int(row[0]),
            "channel_id": int(row[1]),
            "owner_id": int(row[2]),
            "panel_channel_id": int(row[3]) if row[3] else None,
            "panel_message_id": int(row[4]) if row[4] else None,
            "created_at": row[5],
        }
    except Exception:
        return None


class TempVoiceService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(int(guild_id), "tempvoice.enabled", True))

    def _join_channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(int(guild_id), "tempvoice.join_channel_id") or 0)

    def _panel_channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(int(guild_id), "tempvoice.panel_channel_id") or 0)

    def _category_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(int(guild_id), "tempvoice.category_id") or 0)

    def _name_format(self, guild_id: int) -> str:
        return str(self.settings.get_guild(int(guild_id), "tempvoice.name_format", "{user} - Temp") or "{user} - Temp")

    def _default_limit(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(int(guild_id), "tempvoice.user_limit_default") or 0)

    def _default_bitrate(self, guild_id: int) -> int | None:
        val = int(self.settings.get_guild_int(int(guild_id), "tempvoice.bitrate_default") or 0)
        return val * 1000 if val > 0 else None

    def _default_region(self, guild_id: int) -> str | None:
        val = str(self.settings.get_guild(int(guild_id), "tempvoice.region_default", "auto") or "auto").strip().lower()
        return None if val in {"auto", "automatic", "none"} else val

    def _auto_delete(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(int(guild_id), "tempvoice.auto_delete_empty", True))

    def _panel_mention(self) -> str:
        return em(self.settings, "info", None) or "ℹ️"

    async def handle_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if not self._enabled(member.guild.id) or member.bot:
            return

        if before.channel and (not after.channel or before.channel.id != after.channel.id):
            await self._cleanup_if_empty(member.guild, before.channel)

        if after.channel and after.channel.id == self._join_channel_id(member.guild.id):
            await self._join_to_create(member, after.channel)

    async def handle_channel_delete(self, guild: discord.Guild, channel_id: int):
        try:
            await self.db.delete_tempvoice_room(int(guild.id), int(channel_id))
        except Exception:
            pass

    async def _cleanup_if_empty(self, guild: discord.Guild, channel: discord.VoiceChannel):
        if not self._auto_delete(guild.id):
            return
        room = _normalize_room(await self.db.get_tempvoice_room_by_channel(guild.id, channel.id))
        if not room:
            return
        if len(channel.members) > 0:
            return
        try:
            await channel.delete(reason="TempVoice leer")
        except Exception:
            pass
        try:
            await self._delete_panel_message(guild, room)
        except Exception:
            pass
        try:
            await self.db.delete_tempvoice_room(int(guild.id), int(channel.id))
        except Exception:
            pass

    async def _delete_panel_message(self, guild: discord.Guild, room: dict):
        if not room:
            return
        channel_id = room.get("panel_channel_id")
        message_id = room.get("panel_message_id")
        if not channel_id or not message_id:
            return
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return
        try:
            msg = await ch.fetch_message(int(message_id))
            await msg.delete()
        except Exception:
            pass

    async def _join_to_create(self, member: discord.Member, join_channel: discord.VoiceChannel):
        guild = member.guild
        existing = _normalize_room(await self.db.get_tempvoice_room_by_owner(guild.id, member.id))
        if existing:
            ch = guild.get_channel(int(existing["channel_id"]))
            if isinstance(ch, discord.VoiceChannel):
                try:
                    await member.move_to(ch)
                except Exception:
                    pass
                await self.refresh_panel(guild, ch.id)
                return
            try:
                await self.db.delete_tempvoice_room(int(guild.id), int(existing["channel_id"]))
            except Exception:
                pass

        category = None
        cat_id = self._category_id(guild.id)
        if cat_id:
            category = guild.get_channel(cat_id)
            if not isinstance(category, discord.CategoryChannel):
                category = None
        if not category and join_channel.category:
            category = join_channel.category

        name = self._name_format(guild.id).format(user=member.display_name, user_id=member.id)
        name = name[:90]
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
            member: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                manage_channels=True,
                move_members=True,
                mute_members=True,
                deafen_members=True,
            ),
        }
        bitrate = self._default_bitrate(guild.id)
        if bitrate and bitrate > guild.bitrate_limit:
            bitrate = guild.bitrate_limit
        user_limit = self._default_limit(guild.id)

        created = await guild.create_voice_channel(
            name=name,
            category=category,
            overwrites=overwrites,
            user_limit=max(0, int(user_limit)),
            bitrate=bitrate or None,
            rtc_region=self._default_region(guild.id),
            reason="TempVoice create",
        )
        try:
            await member.move_to(created)
        except Exception:
            pass

        panel_msg = await self._send_panel_message(guild, member, created)
        await self.db.create_tempvoice_room(
            guild.id,
            created.id,
            member.id,
            created.id,
            int(panel_msg.id) if panel_msg else None,
        )

    async def _send_panel_message(
        self,
        guild: discord.Guild,
        owner: discord.Member,
        channel: discord.VoiceChannel,
    ):
        ch = channel if isinstance(channel, discord.abc.Messageable) else None
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel.id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return None
        locked = self._is_locked(guild, channel)
        private = self._is_private(guild, channel)
        container = build_tempvoice_panel_container(self.settings, guild, owner, channel, locked, private)
        view = TempVoicePanelView(self, channel.id, owner.id, locked, private, container=container)
        try:
            return await ch.send(content=f"{owner.mention} {self._panel_mention()}", view=view)
        except Exception:
            return None

    async def refresh_panel(self, guild: discord.Guild, channel_id: int):
        room = _normalize_room(await self.db.get_tempvoice_room_by_channel(guild.id, channel_id))
        if not room:
            return
        ch = guild.get_channel(int(channel_id))
        if not isinstance(ch, discord.VoiceChannel):
            return
        owner = guild.get_member(int(room["owner_id"]))
        if not owner:
            try:
                owner = await guild.fetch_member(int(room["owner_id"]))
            except Exception:
                return
        panel_id = room.get("panel_channel_id")
        panel_msg_id = room.get("panel_message_id")
        panel_ch = None
        if panel_id and int(panel_id) == int(ch.id):
            panel_ch = guild.get_channel(int(panel_id))
        if not panel_ch:
            panel_ch = ch if isinstance(ch, discord.abc.Messageable) else None
        if not panel_ch or not isinstance(panel_ch, discord.abc.Messageable):
            return
        locked = self._is_locked(guild, ch)
        private = self._is_private(guild, ch)
        container = build_tempvoice_panel_container(self.settings, guild, owner, ch, locked, private)
        view = TempVoicePanelView(self, ch.id, owner.id, locked, private, container=container)
        if panel_msg_id:
            try:
                msg = await panel_ch.fetch_message(int(panel_msg_id))
                await msg.edit(content=f"{owner.mention} {self._panel_mention()}", view=view)
                return
            except Exception:
                pass
        try:
            msg = await panel_ch.send(content=f"{owner.mention} {self._panel_mention()}", view=view)
            await self.db.set_tempvoice_panel_message(guild.id, ch.id, panel_ch.id, msg.id)
        except Exception:
            pass

    def _is_locked(self, guild: discord.Guild, channel: discord.VoiceChannel) -> bool:
        ow = channel.overwrites_for(guild.default_role)
        return ow.connect is False

    def _is_private(self, guild: discord.Guild, channel: discord.VoiceChannel) -> bool:
        ow = channel.overwrites_for(guild.default_role)
        return ow.view_channel is False

    async def _get_channel_and_room(self, interaction: discord.Interaction, channel_id: int):
        if not interaction.guild:
            return None, None, "Nur im Server nutzbar."
        ch = interaction.guild.get_channel(int(channel_id))
        if not isinstance(ch, discord.VoiceChannel):
            return None, None, "Voice-Channel nicht gefunden."
        room = _normalize_room(await self.db.get_tempvoice_room_by_channel(interaction.guild.id, ch.id))
        if not room:
            return None, None, "Kein Temp-Voice gefunden."
        return ch, room, None

    async def _ensure_owner(self, interaction: discord.Interaction, room: dict) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
            return False
        if interaction.user.id != int(room["owner_id"]) and not is_staff(self.settings, interaction.user):
            await interaction.response.send_message("Nur der Owner darf das nutzen.", ephemeral=True)
            return False
        return True

    async def rename_channel(self, interaction: discord.Interaction, channel_id: int, name: str):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        name = str(name or "").strip()
        if not name:
            return await interaction.response.send_message("Bitte einen Namen angeben.", ephemeral=True)
        try:
            await ch.edit(name=name[:90])
        except Exception:
            return await interaction.response.send_message("Konnte den Namen nicht setzen.", ephemeral=True)
        await self.refresh_panel(interaction.guild, ch.id)
        await interaction.response.send_message("Name aktualisiert.", ephemeral=True)

    async def set_user_limit(self, interaction: discord.Interaction, channel_id: int, raw_limit: str):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        try:
            limit = int(str(raw_limit).strip())
        except Exception:
            return await interaction.response.send_message("Limit muss eine Zahl sein.", ephemeral=True)
        limit = max(0, min(99, limit))
        try:
            await ch.edit(user_limit=limit)
        except Exception:
            return await interaction.response.send_message("Konnte das Limit nicht setzen.", ephemeral=True)
        await self.refresh_panel(interaction.guild, ch.id)
        await interaction.response.send_message("Limit aktualisiert.", ephemeral=True)

    async def set_bitrate(self, interaction: discord.Interaction, channel_id: int, raw_bitrate: str):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        try:
            kbps = int(str(raw_bitrate).strip())
        except Exception:
            return await interaction.response.send_message("Bitrate muss eine Zahl sein.", ephemeral=True)
        kbps = max(8, kbps)
        max_kbps = int(getattr(interaction.guild, "bitrate_limit", 96000)) // 1000
        kbps = min(kbps, max_kbps)
        try:
            await ch.edit(bitrate=kbps * 1000)
        except Exception:
            return await interaction.response.send_message("Konnte die Bitrate nicht setzen.", ephemeral=True)
        await self.refresh_panel(interaction.guild, ch.id)
        await interaction.response.send_message("Bitrate aktualisiert.", ephemeral=True)

    async def set_region(self, interaction: discord.Interaction, channel_id: int, region: str):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        region_key = str(region or "").strip().lower()
        if region_key in {"auto", "automatic", "none"}:
            region_key = None
        try:
            await ch.edit(rtc_region=region_key)
        except Exception:
            return await interaction.response.send_message("Konnte die Region nicht setzen.", ephemeral=True)
        await self.refresh_panel(interaction.guild, ch.id)
        await interaction.response.send_message("Region aktualisiert.", ephemeral=True)

    async def toggle_lock(self, interaction: discord.Interaction, channel_id: int):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        ow = ch.overwrites_for(interaction.guild.default_role)
        locked = ow.connect is False
        ow.connect = None if locked else False
        try:
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
        except Exception:
            return await interaction.response.send_message("Konnte den Lock nicht aendern.", ephemeral=True)
        await self.refresh_panel(interaction.guild, ch.id)
        await interaction.response.send_message("Lock aktualisiert.", ephemeral=True)

    async def toggle_privacy(self, interaction: discord.Interaction, channel_id: int):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        ow = ch.overwrites_for(interaction.guild.default_role)
        private = ow.view_channel is False
        ow.view_channel = None if private else False
        if ow.view_channel is False:
            ow.connect = False
        try:
            await ch.set_permissions(interaction.guild.default_role, overwrite=ow)
        except Exception:
            return await interaction.response.send_message("Konnte den Modus nicht aendern.", ephemeral=True)
        await self.refresh_panel(interaction.guild, ch.id)
        await interaction.response.send_message("Sichtbarkeit aktualisiert.", ephemeral=True)

    async def apply_user_action(
        self,
        interaction: discord.Interaction,
        channel_id: int,
        action: str,
        user: discord.User,
    ):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        if not isinstance(user, discord.Member):
            try:
                user = await interaction.guild.fetch_member(int(user.id))
            except Exception:
                return await interaction.response.send_message("User nicht gefunden.", ephemeral=True)

        if action == "invite":
            return await self._invite_user(interaction, ch, user)
        if action == "block":
            return await self._block_user(interaction, ch, user)
        if action == "unblock":
            return await self._unblock_user(interaction, ch, user)
        if action == "kick":
            return await self._kick_user(interaction, ch, user)
        if action == "mute":
            return await self._mute_user(interaction, ch, user, True)
        if action == "unmute":
            return await self._mute_user(interaction, ch, user, False)
        if action == "deafen":
            return await self._deafen_user(interaction, ch, user, True)
        if action == "undeafen":
            return await self._deafen_user(interaction, ch, user, False)
        if action == "transfer":
            return await self._transfer_owner(interaction, ch, user)

        await interaction.response.send_message("Unbekannte Aktion.", ephemeral=True)

    async def _invite_user(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member):
        try:
            ow = channel.overwrites_for(member)
            ow.view_channel = True
            ow.connect = True
            await channel.set_permissions(member, overwrite=ow)
        except Exception:
            return await interaction.response.send_message("Konnte nicht einladen.", ephemeral=True)
        try:
            view = build_tempvoice_invite_embed(self.settings, interaction.guild, interaction.user, channel)
            await member.send(view=view)
        except Exception:
            pass
        await interaction.response.send_message(f"{member.mention} eingeladen.", ephemeral=True)

    async def _block_user(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member):
        try:
            ow = channel.overwrites_for(member)
            ow.view_channel = True
            ow.connect = False
            await channel.set_permissions(member, overwrite=ow)
        except Exception:
            return await interaction.response.send_message("Konnte nicht blocken.", ephemeral=True)
        if member.voice and member.voice.channel and member.voice.channel.id == channel.id:
            try:
                await member.move_to(None)
            except Exception:
                pass
        await interaction.response.send_message(f"{member.mention} geblockt.", ephemeral=True)

    async def _unblock_user(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member):
        try:
            await channel.set_permissions(member, overwrite=None)
        except Exception:
            return await interaction.response.send_message("Konnte nicht unblocken.", ephemeral=True)
        await interaction.response.send_message(f"{member.mention} entblockt.", ephemeral=True)

    async def _kick_user(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member):
        if not member.voice or not member.voice.channel or member.voice.channel.id != channel.id:
            return await interaction.response.send_message("User ist nicht im Channel.", ephemeral=True)
        try:
            await member.move_to(None)
        except Exception:
            return await interaction.response.send_message("Konnte User nicht kicken.", ephemeral=True)
        await interaction.response.send_message(f"{member.mention} gekickt.", ephemeral=True)

    async def _mute_user(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member, state: bool):
        if not member.voice or not member.voice.channel or member.voice.channel.id != channel.id:
            return await interaction.response.send_message("User ist nicht im Channel.", ephemeral=True)
        try:
            await member.edit(mute=state)
        except Exception:
            return await interaction.response.send_message("Konnte Mute nicht setzen.", ephemeral=True)
        await interaction.response.send_message(f"{member.mention} {'gemutet' if state else 'entmutet'}.", ephemeral=True)

    async def _deafen_user(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member, state: bool):
        if not member.voice or not member.voice.channel or member.voice.channel.id != channel.id:
            return await interaction.response.send_message("User ist nicht im Channel.", ephemeral=True)
        try:
            await member.edit(deafen=state)
        except Exception:
            return await interaction.response.send_message("Konnte Deafen nicht setzen.", ephemeral=True)
        await interaction.response.send_message(f"{member.mention} {'ge-deafed' if state else 'undeafed'}.", ephemeral=True)

    async def _transfer_owner(self, interaction: discord.Interaction, channel: discord.VoiceChannel, member: discord.Member):
        try:
            await self.db.set_tempvoice_owner(interaction.guild.id, channel.id, member.id)
        except Exception:
            return await interaction.response.send_message("Konnte Owner nicht uebertragen.", ephemeral=True)
        try:
            await channel.set_permissions(interaction.user, overwrite=None)
            ow = channel.overwrites_for(member)
            ow.view_channel = True
            ow.connect = True
            ow.manage_channels = True
            ow.move_members = True
            ow.mute_members = True
            ow.deafen_members = True
            await channel.set_permissions(member, overwrite=ow)
        except Exception:
            pass
        await self.refresh_panel(interaction.guild, channel.id)
        await interaction.response.send_message(f"Owner an {member.mention} uebertragen.", ephemeral=True)

    async def send_panel_for_channel(self, interaction: discord.Interaction, channel_id: int):
        ch, room, err = await self._get_channel_and_room(interaction, channel_id)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)
        if not await self._ensure_owner(interaction, room):
            return
        owner = interaction.guild.get_member(int(room["owner_id"]))
        if not owner:
            try:
                owner = await interaction.guild.fetch_member(int(room["owner_id"]))
            except Exception:
                return await interaction.response.send_message("Owner nicht gefunden.", ephemeral=True)
        msg = await self._send_panel_message(interaction.guild, owner, ch)
        if not msg:
            return await interaction.response.send_message("Panel konnte nicht gesendet werden.", ephemeral=True)
        await self.db.set_tempvoice_panel_message(interaction.guild.id, ch.id, msg.channel.id, msg.id)
        await interaction.response.send_message("Panel gesendet.", ephemeral=True)

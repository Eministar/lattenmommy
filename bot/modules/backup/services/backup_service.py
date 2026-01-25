import json
import io
import asyncio
import urllib.request
from datetime import datetime, timezone
import discord


class BackupService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _exclude(self):
        return self.settings.get("backup.exclude", {}) or {}

    def _exclude_ids(self):
        return {
            "roles": set(int(x) for x in (self.settings.get("backup.exclude_role_ids", []) or []) if int(x)),
            "channels": set(int(x) for x in (self.settings.get("backup.exclude_channel_ids", []) or []) if int(x)),
        }

    def _role_payload(self, role: discord.Role):
        return {
            "id": int(role.id),
            "name": role.name,
            "color": int(role.color.value),
            "hoist": bool(role.hoist),
            "position": int(role.position),
            "permissions": int(role.permissions.value),
            "mentionable": bool(role.mentionable),
            "managed": bool(role.managed),
            "is_default": bool(role.is_default()),
        }

    def _emoji_payload(self, emoji: discord.Emoji):
        return {
            "id": int(emoji.id),
            "name": emoji.name,
            "animated": bool(emoji.animated),
            "roles": [int(r.id) for r in emoji.roles],
            "url": str(emoji.url),
        }

    def _sticker_payload(self, sticker: discord.Sticker):
        tags = getattr(sticker, "tags", None)
        if not tags:
            tags = getattr(sticker, "emoji", None)
        return {
            "id": int(sticker.id),
            "name": sticker.name,
            "description": sticker.description,
            "tags": tags,
            "format": str(sticker.format),
            "url": str(sticker.url),
        }

    def _webhook_payload(self, webhook: discord.Webhook):
        return {
            "id": int(webhook.id),
            "name": webhook.name,
            "channel_id": int(webhook.channel_id) if webhook.channel_id else None,
            "avatar_url": str(webhook.avatar.url) if webhook.avatar else None,
        }

    def _channel_overwrites_payload(self, channel: discord.abc.GuildChannel):
        out = []
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Role):
                target_type = "role"
            elif isinstance(target, discord.Member):
                target_type = "member"
            else:
                continue
            out.append(
                {
                    "type": target_type,
                    "id": int(target.id),
                    "allow": int(overwrite.pair()[0].value),
                    "deny": int(overwrite.pair()[1].value),
                }
            )
        return out

    def _overwrites_signature(self, overwrites: list[dict]) -> list[tuple]:
        sig = []
        for ow in overwrites:
            sig.append((
                str(ow.get("type")),
                int(ow.get("id", 0) or 0),
                int(ow.get("allow", 0) or 0),
                int(ow.get("deny", 0) or 0),
            ))
        return sorted(sig)

    def _channel_payload(self, channel: discord.abc.GuildChannel):
        base = {
            "id": int(channel.id),
            "name": channel.name,
            "type": str(channel.type),
            "position": int(channel.position),
            "category_id": int(channel.category_id) if channel.category_id else None,
            "overwrites": self._channel_overwrites_payload(channel),
        }
        if isinstance(channel, discord.TextChannel):
            base.update(
                {
                    "topic": channel.topic,
                    "nsfw": bool(channel.nsfw),
                    "slowmode_delay": int(channel.slowmode_delay),
                }
            )
        if isinstance(channel, discord.VoiceChannel):
            base.update(
                {
                    "bitrate": int(channel.bitrate),
                    "user_limit": int(channel.user_limit),
                }
            )
        if isinstance(channel, discord.CategoryChannel):
            base.update({})
        if isinstance(channel, discord.ForumChannel):
            base.update(
                {
                    "topic": channel.topic,
                    "nsfw": bool(channel.nsfw),
                    "slowmode_delay": int(channel.slowmode_delay),
                }
            )
        return base

    def _member_roles_payload(self, member: discord.Member):
        roles = [int(r.id) for r in member.roles if not r.is_default()]
        return {
            "id": int(member.id),
            "roles": roles,
        }

    async def create_backup(self, guild: discord.Guild, name: str | None = None):
        exclude = self._exclude()
        exclude_ids = self._exclude_ids()

        payload = {
            "guild_id": int(guild.id),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "roles": [],
            "channels": [],
            "members": [],
            "emojis": [],
            "stickers": [],
            "webhooks": [],
        }

        if not exclude.get("roles", False):
            for role in guild.roles:
                if int(role.id) in exclude_ids["roles"]:
                    continue
                payload["roles"].append(self._role_payload(role))

        if not exclude.get("channels", False):
            for channel in guild.channels:
                if int(channel.id) in exclude_ids["channels"]:
                    continue
                payload["channels"].append(self._channel_payload(channel))

        if not exclude.get("member_roles", False):
            for member in guild.members:
                if member.bot:
                    continue
                payload["members"].append(self._member_roles_payload(member))

        if not exclude.get("emojis", False):
            for emoji in guild.emojis:
                payload["emojis"].append(self._emoji_payload(emoji))

        if not exclude.get("stickers", False):
            for sticker in getattr(guild, "stickers", []):
                payload["stickers"].append(self._sticker_payload(sticker))

        if not exclude.get("webhooks", False):
            try:
                hooks = await guild.webhooks()
            except Exception:
                hooks = []
            for hook in hooks:
                payload["webhooks"].append(self._webhook_payload(hook))

        backup_name = name or datetime.now(timezone.utc).strftime("autosave-%Y%m%d-%H%M")
        backup_json = json.dumps(payload, ensure_ascii=False)
        backup_id = await self.db.create_backup(guild.id, backup_name, backup_json)
        return backup_id, backup_name

    def _resolve_role(self, guild: discord.Guild, role_data: dict):
        rid = int(role_data.get("id", 0) or 0)
        role = guild.get_role(rid) if rid else None
        if role:
            return role
        name = str(role_data.get("name", "") or "").strip()
        if name:
            for r in guild.roles:
                if r.name == name:
                    return r
        return None

    async def _ensure_role(self, guild: discord.Guild, role_data: dict):
        role = self._resolve_role(guild, role_data)
        if role:
            return role, False
        if bool(role_data.get("is_default")):
            return guild.default_role, False
        try:
            role = await guild.create_role(
                name=str(role_data.get("name", "role")),
                colour=discord.Colour(int(role_data.get("color", 0) or 0)),
                hoist=bool(role_data.get("hoist", False)),
                mentionable=bool(role_data.get("mentionable", False)),
                permissions=discord.Permissions(int(role_data.get("permissions", 0) or 0)),
                reason="Backup restore",
            )
            return role, True
        except Exception:
            return None, False

    async def _download_bytes(self, url: str | None):
        if not url:
            return None
        def _read():
            with urllib.request.urlopen(str(url), timeout=10) as resp:
                return resp.read()
        try:
            return await asyncio.to_thread(_read)
        except Exception:
            return None

    def _resolve_emoji(self, guild: discord.Guild, emoji_data: dict):
        eid = int(emoji_data.get("id", 0) or 0)
        if eid:
            for e in guild.emojis:
                if e.id == eid:
                    return e
        name = str(emoji_data.get("name", "") or "")
        for e in guild.emojis:
            if e.name == name:
                return e
        return None

    def _resolve_sticker(self, guild: discord.Guild, sticker_data: dict):
        sid = int(sticker_data.get("id", 0) or 0)
        if sid:
            for s in getattr(guild, "stickers", []):
                if s.id == sid:
                    return s
        name = str(sticker_data.get("name", "") or "")
        for s in getattr(guild, "stickers", []):
            if s.name == name:
                return s
        return None

    def _resolve_webhook(self, hooks: list[discord.Webhook], hook_data: dict):
        hid = int(hook_data.get("id", 0) or 0)
        if hid:
            for h in hooks:
                if h.id == hid:
                    return h
        name = str(hook_data.get("name", "") or "")
        for h in hooks:
            if h.name == name and h.channel_id == hook_data.get("channel_id"):
                return h
        return None

    async def _sync_role(self, role: discord.Role, role_data: dict, allow_update: bool):
        if not allow_update:
            return
        if role.is_default() or role.managed:
            return
        kwargs = {}
        if role.name != role_data.get("name"):
            kwargs["name"] = role_data.get("name")
        if role.colour.value != int(role_data.get("color", 0) or 0):
            kwargs["colour"] = discord.Colour(int(role_data.get("color", 0) or 0))
        if role.hoist != bool(role_data.get("hoist", False)):
            kwargs["hoist"] = bool(role_data.get("hoist", False))
        if role.mentionable != bool(role_data.get("mentionable", False)):
            kwargs["mentionable"] = bool(role_data.get("mentionable", False))
        if role.permissions.value != int(role_data.get("permissions", 0) or 0):
            kwargs["permissions"] = discord.Permissions(int(role_data.get("permissions", 0) or 0))
        if kwargs:
            try:
                await role.edit(reason="Backup restore", **kwargs)
            except Exception:
                pass

    def _build_overwrites(self, guild: discord.Guild, overwrites_data: list, role_map: dict):
        out = {}
        for ow in overwrites_data:
            target_type = ow.get("type")
            tid = int(ow.get("id", 0) or 0)
            target = None
            if target_type == "role":
                target = role_map.get(tid) or guild.get_role(tid)
            elif target_type == "member":
                target = guild.get_member(tid)
            if not target:
                continue
            allow = discord.Permissions(int(ow.get("allow", 0) or 0))
            deny = discord.Permissions(int(ow.get("deny", 0) or 0))
            out[target] = discord.PermissionOverwrite.from_pair(allow, deny)
        return out

    def _channel_match(self, guild: discord.Guild, channel_data: dict):
        cid = int(channel_data.get("id", 0) or 0)
        if cid:
            ch = guild.get_channel(cid)
            if ch:
                return ch
        name = str(channel_data.get("name", "") or "")
        for ch in guild.channels:
            if ch.name == name and str(ch.type) == str(channel_data.get("type")):
                return ch
        return None

    async def _ensure_channel(self, guild: discord.Guild, channel_data: dict, category_map: dict, role_map: dict, allow_permissions: bool):
        channel = self._channel_match(guild, channel_data)
        if channel:
            return channel, False
        ch_type = str(channel_data.get("type"))
        overwrites = self._build_overwrites(guild, channel_data.get("overwrites", []), role_map) if allow_permissions else {}
        cat_id = channel_data.get("category_id")
        category = category_map.get(int(cat_id)) if cat_id else None
        try:
            if ch_type == "category":
                channel = await guild.create_category(
                    name=channel_data.get("name", "category"),
                    overwrites=overwrites,
                    reason="Backup restore",
                )
            elif ch_type == "text":
                channel = await guild.create_text_channel(
                    name=channel_data.get("name", "text"),
                    category=category,
                    topic=channel_data.get("topic"),
                    nsfw=bool(channel_data.get("nsfw", False)),
                    slowmode_delay=int(channel_data.get("slowmode_delay", 0) or 0),
                    overwrites=overwrites,
                    reason="Backup restore",
                )
            elif ch_type == "voice":
                channel = await guild.create_voice_channel(
                    name=channel_data.get("name", "voice"),
                    category=category,
                    bitrate=int(channel_data.get("bitrate", 64000) or 64000),
                    user_limit=int(channel_data.get("user_limit", 0) or 0),
                    overwrites=overwrites,
                    reason="Backup restore",
                )
            elif ch_type == "forum":
                channel = await guild.create_forum_channel(
                    name=channel_data.get("name", "forum"),
                    category=category,
                    topic=channel_data.get("topic"),
                    nsfw=bool(channel_data.get("nsfw", False)),
                    slowmode_delay=int(channel_data.get("slowmode_delay", 0) or 0),
                    overwrites=overwrites,
                    reason="Backup restore",
                )
            else:
                return None, False
            return channel, True
        except Exception:
            return None, False

    async def _sync_channel(self, channel: discord.abc.GuildChannel, channel_data: dict, category_map: dict, role_map: dict, allow_update: bool, allow_permissions: bool):
        if not allow_update:
            return
        kwargs = {}
        if channel.position != int(channel_data.get("position", channel.position)):
            kwargs["position"] = int(channel_data.get("position", channel.position))
        if channel.name != channel_data.get("name"):
            kwargs["name"] = channel_data.get("name")
        if isinstance(channel, discord.TextChannel):
            if channel.topic != channel_data.get("topic"):
                kwargs["topic"] = channel_data.get("topic")
            if channel.nsfw != bool(channel_data.get("nsfw", False)):
                kwargs["nsfw"] = bool(channel_data.get("nsfw", False))
            if channel.slowmode_delay != int(channel_data.get("slowmode_delay", 0) or 0):
                kwargs["slowmode_delay"] = int(channel_data.get("slowmode_delay", 0) or 0)
        if isinstance(channel, discord.ForumChannel):
            if channel.topic != channel_data.get("topic"):
                kwargs["topic"] = channel_data.get("topic")
            if channel.nsfw != bool(channel_data.get("nsfw", False)):
                kwargs["nsfw"] = bool(channel_data.get("nsfw", False))
            if channel.slowmode_delay != int(channel_data.get("slowmode_delay", 0) or 0):
                kwargs["slowmode_delay"] = int(channel_data.get("slowmode_delay", 0) or 0)
        if isinstance(channel, discord.VoiceChannel):
            if channel.bitrate != int(channel_data.get("bitrate", 0) or 0):
                kwargs["bitrate"] = int(channel_data.get("bitrate", 0) or 0)
            if channel.user_limit != int(channel_data.get("user_limit", 0) or 0):
                kwargs["user_limit"] = int(channel_data.get("user_limit", 0) or 0)
        if channel.category_id != channel_data.get("category_id"):
            cat_id = channel_data.get("category_id")
            category = category_map.get(int(cat_id)) if cat_id else None
            kwargs["category"] = category
        if allow_permissions:
            kwargs["overwrites"] = self._build_overwrites(guild=channel.guild, overwrites_data=channel_data.get("overwrites", []), role_map=role_map)
        if kwargs:
            try:
                await channel.edit(reason="Backup restore", **kwargs)
            except Exception:
                pass

    async def load_backup(self, guild: discord.Guild, backup_row, name: str | None = None):
        if not backup_row:
            return False, "backup_not_found"
        _, _, payload_json, _ = backup_row
        try:
            data = json.loads(payload_json)
        except Exception:
            return False, "backup_invalid_json"

        exclude = self._exclude()
        exclude_ids = self._exclude_ids()

        role_map = {}
        if not exclude.get("roles", False):
            for role_data in data.get("roles", []):
                rid = int(role_data.get("id", 0) or 0)
                if rid in exclude_ids["roles"]:
                    continue
                role, _ = await self._ensure_role(guild, role_data)
                if role:
                    role_map[rid] = role
                    await self._sync_role(role, role_data, allow_update=True)

            for role_data in sorted(data.get("roles", []), key=lambda r: int(r.get("position", 0))):
                rid = int(role_data.get("id", 0) or 0)
                role = role_map.get(rid)
                if role and not role.is_default() and not role.managed:
                    try:
                        await role.edit(position=int(role_data.get("position", role.position)), reason="Backup restore")
                    except Exception:
                        pass

        category_map = {}
        if not exclude.get("channels", False):
            categories = [c for c in data.get("channels", []) if c.get("type") == "category"]
            for cat_data in categories:
                cid = int(cat_data.get("id", 0) or 0)
                if cid in exclude_ids["channels"]:
                    continue
                channel, _ = await self._ensure_channel(guild, cat_data, category_map, role_map, allow_permissions=not exclude.get("permissions", False))
                if channel:
                    category_map[cid] = channel
                    await self._sync_channel(channel, cat_data, category_map, role_map, allow_update=True, allow_permissions=not exclude.get("permissions", False))

            others = [c for c in data.get("channels", []) if c.get("type") != "category"]
            for ch_data in others:
                cid = int(ch_data.get("id", 0) or 0)
                if cid in exclude_ids["channels"]:
                    continue
                channel, _ = await self._ensure_channel(guild, ch_data, category_map, role_map, allow_permissions=not exclude.get("permissions", False))
                if channel:
                    await self._sync_channel(channel, ch_data, category_map, role_map, allow_update=True, allow_permissions=not exclude.get("permissions", False))

        if not exclude.get("member_roles", False) and not exclude.get("roles", False):
            for mem_data in data.get("members", []):
                member = guild.get_member(int(mem_data.get("id", 0) or 0))
                if not member or member.bot:
                    continue
                desired_role_ids = [int(r) for r in mem_data.get("roles", []) if int(r) not in exclude_ids["roles"]]
                desired_roles = []
                for rid in desired_role_ids:
                    role = role_map.get(rid) or guild.get_role(rid)
                    if role and not role.managed and not role.is_default():
                        desired_roles.append(role)
                current_roles = [r for r in member.roles if not r.is_default() and not r.managed]
                desired_set = {r.id for r in desired_roles}
                current_set = {r.id for r in current_roles}
                to_add = [r for r in desired_roles if r.id not in current_set]
                to_remove = [r for r in current_roles if r.id not in desired_set and r.id not in exclude_ids["roles"]]
                try:
                    if to_add:
                        await member.add_roles(*to_add, reason="Backup restore")
                    if to_remove:
                        await member.remove_roles(*to_remove, reason="Backup restore")
                except Exception:
                    pass

        if not exclude.get("emojis", False):
            for emoji_data in data.get("emojis", []):
                emoji = self._resolve_emoji(guild, emoji_data)
                if not emoji:
                    img = await self._download_bytes(emoji_data.get("url"))
                    if img:
                        try:
                            await guild.create_custom_emoji(
                                name=emoji_data.get("name", "emoji"),
                                image=img,
                                roles=[guild.get_role(rid) for rid in emoji_data.get("roles", []) if guild.get_role(rid)],
                                reason="Backup restore",
                            )
                        except Exception:
                            pass
                else:
                    try:
                        await emoji.edit(
                            name=emoji_data.get("name", emoji.name),
                            roles=[guild.get_role(rid) for rid in emoji_data.get("roles", []) if guild.get_role(rid)],
                            reason="Backup restore",
                        )
                    except Exception:
                        pass

        if not exclude.get("stickers", False):
            for sticker_data in data.get("stickers", []):
                sticker = self._resolve_sticker(guild, sticker_data)
                if not sticker:
                    img = await self._download_bytes(sticker_data.get("url"))
                    if img:
                        try:
                            file = discord.File(fp=io.BytesIO(img), filename=f"{sticker_data.get('name','sticker')}.png")
                            await guild.create_sticker(
                                name=sticker_data.get("name", "sticker"),
                                description=sticker_data.get("description") or "—",
                                tags=sticker_data.get("tags") or sticker_data.get("emoji") or "🙂",
                                file=file,
                                reason="Backup restore",
                            )
                        except Exception:
                            pass
                else:
                    try:
                        current_tags = getattr(sticker, "tags", None) or getattr(sticker, "emoji", None)
                        await guild.edit_sticker(
                            sticker,
                            name=sticker_data.get("name", sticker.name),
                            description=sticker_data.get("description", sticker.description),
                            tags=sticker_data.get("tags", current_tags),
                            reason="Backup restore",
                        )
                    except Exception:
                        pass

        if not exclude.get("webhooks", False):
            try:
                hooks = await guild.webhooks()
            except Exception:
                hooks = []
            for hook_data in data.get("webhooks", []):
                hook = self._resolve_webhook(hooks, hook_data)
                ch = guild.get_channel(int(hook_data.get("channel_id") or 0))
                if not isinstance(ch, discord.abc.GuildChannel):
                    continue
                if not hook:
                    avatar = await self._download_bytes(hook_data.get("avatar_url"))
                    try:
                        await ch.create_webhook(name=hook_data.get("name", "webhook"), avatar=avatar, reason="Backup restore")
                    except Exception:
                        pass
                else:
                    try:
                        avatar = await self._download_bytes(hook_data.get("avatar_url"))
                        await hook.edit(name=hook_data.get("name", hook.name), avatar=avatar, reason="Backup restore")
                    except Exception:
                        pass

        return True, None

    async def diff_backup(self, guild: discord.Guild, backup_row):
        if not backup_row:
            return None
        _, _, payload_json, _ = backup_row
        try:
            data = json.loads(payload_json)
        except Exception:
            return None

        exclude = self._exclude()
        exclude_ids = self._exclude_ids()
        out = {
            "roles_missing": 0,
            "roles_update": 0,
            "channels_missing": 0,
            "channels_update": 0,
            "permissions_update": 0,
            "member_roles_changes": 0,
            "emojis_missing": 0,
            "emojis_update": 0,
            "stickers_missing": 0,
            "stickers_update": 0,
            "webhooks_missing": 0,
            "webhooks_update": 0,
        }

        role_map = {}
        if not exclude.get("roles", False):
            for role_data in data.get("roles", []):
                rid = int(role_data.get("id", 0) or 0)
                if rid in exclude_ids["roles"]:
                    continue
                role = self._resolve_role(guild, role_data)
                if not role:
                    out["roles_missing"] += 1
                else:
                    role_map[rid] = role
                    if (
                        role.name != role_data.get("name")
                        or role.colour.value != int(role_data.get("color", 0) or 0)
                        or role.hoist != bool(role_data.get("hoist", False))
                        or role.mentionable != bool(role_data.get("mentionable", False))
                        or role.permissions.value != int(role_data.get("permissions", 0) or 0)
                    ):
                        out["roles_update"] += 1

        if not exclude.get("channels", False):
            for ch_data in data.get("channels", []):
                cid = int(ch_data.get("id", 0) or 0)
                if cid in exclude_ids["channels"]:
                    continue
                ch = self._channel_match(guild, ch_data)
                if not ch:
                    out["channels_missing"] += 1
                else:
                    if ch.name != ch_data.get("name"):
                        out["channels_update"] += 1
                    if not exclude.get("permissions", False):
                        current_ow = self._channel_overwrites_payload(ch)
                        if self._overwrites_signature(current_ow) != self._overwrites_signature(ch_data.get("overwrites", [])):
                            out["permissions_update"] += 1

        if not exclude.get("member_roles", False) and not exclude.get("roles", False):
            for mem_data in data.get("members", []):
                member = guild.get_member(int(mem_data.get("id", 0) or 0))
                if not member or member.bot:
                    continue
                desired_role_ids = [int(r) for r in mem_data.get("roles", []) if int(r) not in exclude_ids["roles"]]
                current_roles = [r for r in member.roles if not r.is_default() and not r.managed]
                current_set = {r.id for r in current_roles}
                if set(desired_role_ids) != current_set:
                    out["member_roles_changes"] += 1

        if not exclude.get("emojis", False):
            for emoji_data in data.get("emojis", []):
                emoji = self._resolve_emoji(guild, emoji_data)
                if not emoji:
                    out["emojis_missing"] += 1
                else:
                    if emoji.name != emoji_data.get("name"):
                        out["emojis_update"] += 1

        if not exclude.get("stickers", False):
            for sticker_data in data.get("stickers", []):
                sticker = self._resolve_sticker(guild, sticker_data)
                if not sticker:
                    out["stickers_missing"] += 1
                else:
                    if sticker.name != sticker_data.get("name"):
                        out["stickers_update"] += 1

        if not exclude.get("webhooks", False):
            try:
                hooks = await guild.webhooks()
            except Exception:
                hooks = []
            for hook_data in data.get("webhooks", []):
                hook = self._resolve_webhook(hooks, hook_data)
                if not hook:
                    out["webhooks_missing"] += 1
                else:
                    if hook.name != hook_data.get("name"):
                        out["webhooks_update"] += 1

        return out

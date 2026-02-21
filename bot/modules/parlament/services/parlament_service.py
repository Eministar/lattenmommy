from __future__ import annotations

import json
import re
from urllib.parse import urlparse
from datetime import datetime, timezone
import discord

from bot.core.perms import is_staff
from bot.utils.assets import Banners
from bot.utils.emojis import em
from bot.modules.parlament.formatting.parlament_embeds import (
    build_parliament_panel_embed,
    build_parliament_vote_container,
)
from bot.modules.parlament.views.vote_view import ParliamentVoteView
from bot.modules.parlament.views.party_views import PartySettingsPanelView


class ParliamentService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _g(self, guild_id: int, key: str, default=None):
        return self.settings.get_guild(guild_id, key, default)

    def _gi(self, guild_id: int, key: str, default: int = 0) -> int:
        return int(self.settings.get_guild_int(guild_id, key, default))

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "parlament.enabled", True))

    def _panel_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.panel_channel_id", 0)

    def _vote_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.vote_channel_id", 0)

    def _candidate_role_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.candidate_role_id", 0)

    def _member_role_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.member_role_id", 0)

    def _party_panel_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.parties.panel_channel_id", 0)

    def _party_forum_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.parties.forum_channel_id", 0)

    def _party_request_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "parlament.parties.request_channel_id", self._party_panel_channel_id(guild_id))

    def _party_team_role_ids(self, guild_id: int) -> list[int]:
        raw = self._g(guild_id, "parlament.parties.team_role_ids", []) or []
        out = []
        for value in raw:
            try:
                out.append(int(value))
            except Exception:
                continue
        return out

    def _party_category_prefix(self, guild_id: int) -> str:
        return str(self._g(guild_id, "parlament.parties.category_prefix", "🏛️ Partei") or "🏛️ Partei").strip()

    def _exempt_user_ids(self, guild_id: int) -> set[int]:
        raw = self._g(guild_id, "parlament.member_role_exempt_user_ids", []) or []
        out = set()
        for v in raw:
            try:
                out.add(int(v))
            except Exception:
                continue
        return out

    def _exempt_role_ids(self, guild_id: int) -> set[int]:
        raw = self._g(guild_id, "parlament.member_role_exempt_role_ids", []) or []
        out = set()
        for v in raw:
            try:
                out.add(int(v))
            except Exception:
                continue
        return out

    def _fixed_member_ids(self, guild_id: int) -> list[int]:
        raw = self._g(guild_id, "parlament.fixed_member_user_ids", []) or []
        out = []
        for v in raw:
            try:
                out.append(int(v))
            except Exception:
                continue
        return out

    async def _get_channel(self, guild: discord.Guild, channel_id: int) -> discord.TextChannel | None:
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await guild.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if isinstance(ch, discord.TextChannel):
            return ch
        return None

    def _get_role(self, guild: discord.Guild, role_id: int) -> discord.Role | None:
        if not role_id:
            return None
        return guild.get_role(int(role_id))

    async def _fetch_members(self, guild: discord.Guild) -> list[discord.Member]:
        members = list(getattr(guild, "members", []) or [])
        if members:
            return members
        members = []
        try:
            async for member in guild.fetch_members(limit=None):
                members.append(member)
        except Exception:
            members = []
        return members

    async def _resolve_candidates(self, guild: discord.Guild) -> list[discord.Member]:
        role = self._get_role(guild, self._candidate_role_id(guild.id))
        if not role:
            return []
        members = await self._fetch_members(guild)
        return [m for m in members if role in getattr(m, "roles", [])]

    async def _resolve_members(self, guild: discord.Guild) -> list[discord.Member]:
        role = self._get_role(guild, self._member_role_id(guild.id))
        if not role:
            return []
        members = await self._fetch_members(guild)
        return [m for m in members if role in getattr(m, "roles", [])]

    def _candidate_options(self, guild: discord.Guild, candidate_ids: list[int]) -> list[tuple[int, str]]:
        options = []
        for cid in candidate_ids:
            member = guild.get_member(int(cid))
            label = member.display_name if member else f"Kandidat {int(cid)}"
            options.append((int(cid), label))
        return options

    async def update_panel(self, guild: discord.Guild):
        if not guild or not self._enabled(guild.id):
            return

        channel = await self._get_channel(guild, self._panel_channel_id(guild.id))
        if not channel:
            return

        candidate_role_id = self._candidate_role_id(guild.id)
        member_role_id = self._member_role_id(guild.id)
        if not candidate_role_id or not member_role_id:
            return

        candidates = await self._resolve_candidates(guild)
        members = await self._resolve_members(guild)

        fixed_ids = self._fixed_member_ids(guild.id)
        fixed_members = []
        for uid in fixed_ids:
            m = guild.get_member(int(uid))
            if m:
                fixed_members.append(m)

        candidate_ids = {int(m.id) for m in candidates}
        members = [m for m in members if int(m.id) not in candidate_ids and int(m.id) not in {int(x.id) for x in fixed_members}]

        user_ids = [int(m.id) for m in candidates] + [int(m.id) for m in members] + [int(m.id) for m in fixed_members]
        rows = await self.db.list_parliament_stats(guild.id, user_ids)
        stats_map = {int(r[1]): (int(r[2]), int(r[3])) for r in rows or []}

        view = build_parliament_panel_embed(
            self.settings,
            guild,
            candidates,
            members,
            stats_map,
            fixed_members=fixed_members,
            updated_at=datetime.now(timezone.utc),
        )

        message_id = self._gi(guild.id, "parlament.panel_message_id", 0)
        msg = None
        if message_id:
            try:
                msg = await channel.fetch_message(int(message_id))
            except Exception:
                msg = None
        if msg:
            try:
                await msg.edit(view=view)
                return
            except Exception:
                pass

        try:
            msg = await channel.send(view=view)
            await self.settings.set_guild_override(self.db, guild.id, "parlament.panel_message_id", int(msg.id))
        except Exception:
            pass

    async def start_vote(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        if not self._enabled(interaction.guild.id):
            return await interaction.response.send_message("Parlament ist deaktiviert.", ephemeral=True)

        open_vote = await self.db.get_open_parliament_vote(interaction.guild.id)
        if open_vote:
            return await interaction.response.send_message("Es läuft bereits ein Votum.", ephemeral=True)

        candidate_role = self._get_role(interaction.guild, self._candidate_role_id(interaction.guild.id))
        member_role = self._get_role(interaction.guild, self._member_role_id(interaction.guild.id))
        if not candidate_role or not member_role:
            return await interaction.response.send_message("Rollen sind nicht konfiguriert.", ephemeral=True)

        channel = await self._get_channel(interaction.guild, self._vote_channel_id(interaction.guild.id))
        if not channel:
            return await interaction.response.send_message("Vote-Channel ist nicht konfiguriert.", ephemeral=True)

        candidates = await self._resolve_candidates(interaction.guild)
        if not candidates:
            return await interaction.response.send_message("Keine Kandidaten gefunden.", ephemeral=True)
        if len(candidates) > 25:
            return await interaction.response.send_message("Zu viele Kandidaten (max. 25).", ephemeral=True)

        for m in candidates:
            try:
                await self.db.increment_parliament_candidated(interaction.guild.id, int(m.id), 1)
            except Exception:
                continue

        exempt_users = self._exempt_user_ids(interaction.guild.id)
        exempt_roles = self._exempt_role_ids(interaction.guild.id)
        members = await self._resolve_members(interaction.guild)
        for m in members:
            if int(m.id) in exempt_users:
                continue
            if exempt_roles and any(int(r.id) in exempt_roles for r in getattr(m, "roles", []) or []):
                continue
            try:
                await m.remove_roles(member_role, reason="Parlament: neues Votum")
            except Exception:
                continue

        candidate_ids = [int(m.id) for m in candidates]
        vote_id = await self.db.create_parliament_vote(
            interaction.guild.id,
            int(channel.id),
            json.dumps(candidate_ids),
            int(interaction.user.id),
        )

        created_at = datetime.now(timezone.utc)
        counts = {}
        container = build_parliament_vote_container(
            self.settings,
            interaction.guild,
            candidates,
            counts,
            "OFFEN",
            created_at=created_at,
        )
        view = ParliamentVoteView(
            self,
            vote_id,
            self._candidate_options(interaction.guild, candidate_ids),
            container=container,
            include_select=True,
        )

        msg = await channel.send(view=view)
        await self.db.set_parliament_vote_message(vote_id, int(msg.id))

        await interaction.response.send_message("Votum gestartet.", ephemeral=True)
        try:
            await self.update_panel(interaction.guild)
        except Exception:
            pass

    async def stop_vote(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        if not self._enabled(interaction.guild.id):
            return await interaction.response.send_message("Parlament ist deaktiviert.", ephemeral=True)

        row = await self.db.get_open_parliament_vote(interaction.guild.id)
        if not row:
            return await interaction.response.send_message("Kein aktives Votum gefunden.", ephemeral=True)

        vote_id = int(row[0])
        channel_id = int(row[2])
        message_id = int(row[3] or 0)
        candidate_ids_json = str(row[4] or "[]")
        created_at_raw = row[7]

        try:
            candidate_ids = json.loads(candidate_ids_json)
        except Exception:
            candidate_ids = []

        candidates = []
        for cid in candidate_ids:
            try:
                m = interaction.guild.get_member(int(cid))
            except Exception:
                m = None
            if m:
                candidates.append(m)

        counts = await self.db.count_parliament_vote_entries(vote_id)
        max_votes = max(counts.values()) if counts else 0
        winner_ids = [cid for cid in candidate_ids if int(counts.get(int(cid), 0)) == int(max_votes)] if max_votes else []

        member_role = self._get_role(interaction.guild, self._member_role_id(interaction.guild.id))
        candidate_role = self._get_role(interaction.guild, self._candidate_role_id(interaction.guild.id))

        if candidate_role:
            for m in await self._resolve_candidates(interaction.guild):
                try:
                    await m.remove_roles(candidate_role, reason="Parlament: Votum beendet")
                except Exception:
                    continue

        winners = []
        if member_role and winner_ids:
            for cid in winner_ids:
                m = interaction.guild.get_member(int(cid))
                if not m:
                    continue
                try:
                    await m.add_roles(member_role, reason="Parlament: gewählt")
                    await self.db.increment_parliament_elected(interaction.guild.id, int(m.id), 1)
                    winners.append(m)
                except Exception:
                    continue

        await self.db.close_parliament_vote(vote_id)

        try:
            created_at = datetime.fromisoformat(str(created_at_raw))
        except Exception:
            created_at = None
        container = build_parliament_vote_container(
            self.settings,
            interaction.guild,
            candidates,
            counts,
            "GESCHLOSSEN",
            created_at=created_at,
        )
        closed_view = discord.ui.LayoutView(timeout=None)
        closed_view.add_item(container)

        try:
            channel = await self._get_channel(interaction.guild, channel_id)
        except Exception:
            channel = None

        if channel and message_id:
            try:
                msg = await channel.fetch_message(int(message_id))
                await msg.edit(view=closed_view)
            except Exception:
                pass

        if channel:
            if winners:
                winner_text = ", ".join([m.mention for m in winners])
                await channel.send(f"🏛️ Votum beendet. Gewählt: {winner_text}")
            elif candidate_ids:
                await channel.send("🏛️ Votum beendet. Keine Stimmen abgegeben.")
            else:
                await channel.send("🏛️ Votum beendet. Keine Kandidaten gefunden.")

        await interaction.response.send_message("Votum beendet.", ephemeral=True)
        try:
            await self.update_panel(interaction.guild)
        except Exception:
            pass

    async def vote(self, interaction: discord.Interaction, vote_id: int, candidate_id: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)

        row = await self.db.get_parliament_vote(vote_id)
        if not row:
            return await interaction.response.send_message("Votum nicht gefunden.", ephemeral=True)
        status = str(row[5])
        if status != "open":
            return await interaction.response.send_message("Votum ist geschlossen.", ephemeral=True)

        try:
            candidate_ids = json.loads(str(row[4] or "[]"))
        except Exception:
            candidate_ids = []

        if int(candidate_id) not in [int(c) for c in candidate_ids]:
            return await interaction.response.send_message("Ungültiger Kandidat.", ephemeral=True)

        existing = await self.db.get_parliament_vote_entry(vote_id, interaction.user.id)
        if existing is not None:
            return await interaction.response.send_message("Du hast bereits gewählt.", ephemeral=True)

        await self.db.add_parliament_vote_entry(vote_id, interaction.user.id, int(candidate_id))

        try:
            view = await self.build_vote_view(interaction.guild, vote_id)
            if view:
                await interaction.message.edit(view=view)
        except Exception:
            pass

        await interaction.response.send_message("Stimme gespeichert.", ephemeral=True)

    async def build_vote_embed(self, guild: discord.Guild, vote_id: int):
        return await self.build_vote_view(guild, vote_id, include_select=False)

    async def build_vote_view(self, guild: discord.Guild, vote_id: int, include_select: bool = True):
        row = await self.db.get_parliament_vote(vote_id)
        if not row:
            return None
        candidate_ids_json = str(row[4] or "[]")
        status = str(row[5])
        created_at_raw = row[7]
        try:
            candidate_ids = json.loads(candidate_ids_json)
        except Exception:
            candidate_ids = []
        candidates = [guild.get_member(int(cid)) for cid in candidate_ids] if guild else []
        candidates = [m for m in candidates if m]
        counts = await self.db.count_parliament_vote_entries(vote_id)
        status_label = "OFFEN" if status == "open" else "GESCHLOSSEN"
        try:
            created_at = datetime.fromisoformat(str(created_at_raw))
        except Exception:
            created_at = None
        container = build_parliament_vote_container(
            self.settings,
            guild,
            candidates,
            counts,
            status_label,
            created_at=created_at,
        )
        if guild:
            options = self._candidate_options(guild, candidate_ids)
        else:
            options = [(int(cid), f"Kandidat {int(cid)}") for cid in candidate_ids]
        allow_select = include_select and status == "open"
        return ParliamentVoteView(self, vote_id, options, container=container, include_select=allow_select)

    async def restore_views(self):
        rows = await self.db.list_open_parliament_votes()
        for row in rows:
            try:
                vote_id, guild_id, channel_id, message_id, candidate_ids_json = row
            except Exception:
                continue
            if not message_id:
                continue
            try:
                candidate_ids = json.loads(str(candidate_ids_json or "[]"))
            except Exception:
                candidate_ids = []
            try:
                guild = self.bot.get_guild(int(guild_id))
                options = self._candidate_options(guild, candidate_ids) if guild else [(int(cid), f"Kandidat {int(cid)}") for cid in candidate_ids]
                view = ParliamentVoteView(self, int(vote_id), options)
                self.bot.add_view(view, message_id=int(message_id))
            except Exception:
                pass

    def _party_slug(self, name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", str(name or "").strip().lower())
        cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
        return cleaned[:48] or "partei"

    def _is_http_url(self, value: str) -> bool:
        raw = str(value or "").strip()
        if not raw:
            return False
        try:
            parsed = urlparse(raw)
            return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
        except Exception:
            return False

    def _extract_first_image_attachment_url(self, message: discord.Message) -> str | None:
        for att in list(getattr(message, "attachments", []) or []):
            url = str(getattr(att, "url", "") or "").strip()
            content_type = str(getattr(att, "content_type", "") or "").lower()
            fn = str(getattr(att, "filename", "") or "").lower()
            if "image/" in content_type or fn.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
                if self._is_http_url(url):
                    return url
        return None

    def _color(self, guild_id: int | None = None) -> int:
        if guild_id:
            raw = str(self.settings.get_guild(guild_id, "design.accent_color", "#B16B91") or "")
        else:
            raw = str(self.settings.get("design.accent_color", "#B16B91") or "")
        value = raw.replace("#", "").strip()
        try:
            return int(value, 16)
        except Exception:
            return 0xB16B91

    async def _send_ephemeral(self, interaction: discord.Interaction, content: str):
        if interaction.response.is_done():
            return await interaction.followup.send(content, ephemeral=True)
        return await interaction.response.send_message(content, ephemeral=True)

    def _extract_user_ids(self, text: str) -> list[int]:
        found = set()
        for raw in re.findall(r"\d{5,22}", str(text or "")):
            try:
                found.add(int(raw))
            except Exception:
                continue
        return list(found)

    async def _get_forum_channel(self, guild: discord.Guild) -> discord.ForumChannel | None:
        channel_id = self._party_forum_channel_id(guild.id)
        if not channel_id:
            return None
        ch = guild.get_channel(channel_id)
        if not ch:
            try:
                ch = await guild.fetch_channel(channel_id)
            except Exception:
                ch = None
        return ch if isinstance(ch, discord.ForumChannel) else None

    async def _get_request_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = self._party_request_channel_id(guild.id)
        if not channel_id:
            return None
        ch = guild.get_channel(channel_id)
        if not ch:
            try:
                ch = await guild.fetch_channel(channel_id)
            except Exception:
                ch = None
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _get_party_thread(self, guild: discord.Guild, thread_id: int) -> discord.Thread | None:
        if not thread_id:
            return None
        thread = guild.get_thread(int(thread_id))
        if thread:
            return thread
        try:
            fetched = await guild.fetch_channel(int(thread_id))
        except Exception:
            fetched = None
        return fetched if isinstance(fetched, discord.Thread) else None

    def _party_overwrites(
        self,
        guild: discord.Guild,
        member_ids: list[int],
        party_role: discord.Role | None = None,
    ) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        if party_role:
            overwrites[party_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                connect=True,
                speak=True,
            )
        for role_id in self._party_team_role_ids(guild.id):
            role = guild.get_role(int(role_id))
            if not role:
                continue
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
                manage_channels=True,
            )
        for user_id in member_ids:
            member = guild.get_member(int(user_id))
            if not member:
                continue
            overwrites[member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                connect=True,
                speak=True,
            )
        return overwrites

    def _party_panel_overwrites(
        self,
        guild: discord.Guild,
        leader_id: int,
        member_ids: list[int],
        party_role: discord.Role | None = None,
    ) -> dict[discord.abc.Snowflake, discord.PermissionOverwrite]:
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False)
        }
        if party_role:
            overwrites[party_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                attach_files=False,
                embed_links=False,
                read_message_history=True,
            )
        for role_id in self._party_team_role_ids(guild.id):
            role = guild.get_role(int(role_id))
            if not role:
                continue
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                read_message_history=True,
                manage_messages=True,
                manage_channels=True,
            )
        for user_id in member_ids:
            member = guild.get_member(int(user_id))
            if not member:
                continue
            can_send = int(user_id) == int(leader_id)
            overwrites[member] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=can_send,
                attach_files=can_send,
                embed_links=can_send,
                read_message_history=True,
            )
        return overwrites

    async def _ensure_party_role(self, guild: discord.Guild, party_row) -> discord.Role | None:
        party = self._party_data(party_row)
        role_id = int(party["party_role_id"] or 0)
        existing = guild.get_role(role_id) if role_id else None
        desired_name = f"🏛️ {party['name']}"[:100]
        if existing:
            if str(existing.name) != desired_name:
                try:
                    await existing.edit(name=desired_name, reason=f"Partei #{party['id']} umbenannt")
                except Exception:
                    pass
            return existing
        try:
            created = await guild.create_role(
                name=desired_name,
                mentionable=False,
                hoist=False,
                reason=f"Partei-Rolle #{party['id']}",
            )
        except Exception:
            return None
        await self.db.set_parliament_party_channels(
            int(party["id"]),
            category_id=int(party["category_id"] or 0) or None,
            text_channel_id=int(party["text_channel_id"] or 0) or None,
            settings_channel_id=int(party["settings_channel_id"] or 0) or None,
            voice_channel_id=int(party["voice_channel_id"] or 0) or None,
            party_role_id=int(created.id),
            settings_message_id=int(party["settings_message_id"] or 0) or None,
        )
        return created

    async def _sync_party_role_members(self, guild: discord.Guild, party_row):
        party = self._party_data(party_row)
        role_id = int(party["party_role_id"] or 0)
        role = guild.get_role(role_id) if role_id else None
        if not role:
            role = await self._ensure_party_role(guild, party_row)
        if not role:
            return
        rows = await self.db.list_parliament_party_members(int(party["id"]))
        member_ids = {int(r[2]) for r in rows}
        for member in list(getattr(role, "members", []) or []):
            if int(member.id) not in member_ids:
                try:
                    await member.remove_roles(role, reason=f"Partei #{party['id']} verlassen")
                except Exception:
                    continue
        for uid in member_ids:
            member = guild.get_member(int(uid))
            if not member or role in getattr(member, "roles", []):
                continue
            try:
                await member.add_roles(role, reason=f"Partei #{party['id']} Mitglied")
            except Exception:
                continue

    def _party_data(self, row) -> dict:
        if not row:
            return {}
        return {
            "id": int(row[0]),
            "guild_id": int(row[1]),
            "name": str(row[2] or ""),
            "slug": str(row[3] or ""),
            "founder_id": int(row[4] or 0),
            "status": str(row[5] or ""),
            "description": str(row[6] or ""),
            "logo_url": str(row[7] or "") if row[7] else "",
            "manifesto_text": str(row[8] or "") if row[8] else "",
            "manifesto_attachments_json": str(row[9] or "") if row[9] else "",
            "forum_thread_id": int(row[10] or 0),
            "category_id": int(row[11] or 0),
            "text_channel_id": int(row[12] or 0),
            "settings_channel_id": int(row[13] or 0),
            "voice_channel_id": int(row[14] or 0),
            "party_role_id": int(row[15] or 0),
            "settings_message_id": int(row[16] or 0),
            "thread_info_message_id": int(row[17] or 0),
        }

    async def _resolve_party_for_panel_interaction(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel:
            return None
        return await self.db.get_parliament_party_by_settings_channel(interaction.guild.id, int(interaction.channel.id))

    async def _is_party_leader(self, interaction: discord.Interaction, party_row) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False
        member_row = await self.db.get_parliament_party_member(int(party_row[0]), int(interaction.user.id))
        return bool(member_row and str(member_row[3]) == "leader")

    async def _build_party_info_view(self, guild: discord.Guild, party_row):
        party = self._party_data(party_row)
        members = await self.db.list_parliament_party_members(int(party["id"]))
        leader_row = next((m for m in members if str(m[3]) == "leader"), None)
        leader_id = int(leader_row[2]) if leader_row else int(party["founder_id"])
        arrow2 = em(self.settings, "arrow2", guild) or "»"
        crown = em(self.settings, "crown", guild) or "👑"
        people = em(self.settings, "people", guild) or "👥"
        page = em(self.settings, "book", guild) or "📘"
        attachments_icon = em(self.settings, "paperclip", guild) or "📎"
        raw = str(party["manifesto_attachments_json"] or "").strip()
        links = []
        if raw:
            try:
                links = [str(x) for x in json.loads(raw) if str(x).strip()]
            except Exception:
                links = []
        manifesto_text = str(party["manifesto_text"] or "").strip() or "Noch kein Programm hinterlegt."
        attach_text = "\n".join(links[:8]) if links else "Keine Anhänge."
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_colour=self._color(guild.id))
        try:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=Banners.PARLIAMENT)
            logo_url = str(party["logo_url"] or "").strip()
            if logo_url and self._is_http_url(logo_url):
                gallery.add_item(media=logo_url)
            container.add_item(gallery)
            container.add_item(discord.ui.Separator())
        except Exception:
            pass
        status_label = str(party["status"] or "unbekannt").upper()
        container.add_item(
            discord.ui.TextDisplay(
                f"**🏛️ 𑁉 PARTEI – {party['name'].upper()}**\n"
                f"{arrow2} Öffentliche Informationen zur Partei.\n\n"
                f"┏`🆔` - ID: **#{party['id']}**\n"
                f"┣`🏷️` - Status: **{status_label}**\n"
                f"┣`{crown}` - Chef: <@{leader_id}>\n"
                f"┗`{people}` - Mitglieder: **{len(members)}**"
            )
        )
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**📝 Beschreibung**\n{str(party['description'] or 'Keine Beschreibung.')[:1200]}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**{page} Parteiprogramm**\n{manifesto_text[:1200]}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**{attachments_icon} Anhänge**\n{attach_text[:1200]}"))
        view.add_item(container)
        return view

    async def _sync_party_info_message(self, guild: discord.Guild, party_row):
        party = self._party_data(party_row)
        thread_id = int(party["forum_thread_id"])
        if not thread_id:
            return
        thread = await self._get_party_thread(guild, thread_id)
        if not thread:
            return
        view = await self._build_party_info_view(guild, party_row)
        marker = f"starry:party:info:{int(party['id'])}"
        message_id = int(party["thread_info_message_id"])
        msg = None
        if message_id:
            try:
                msg = await thread.fetch_message(message_id)
            except Exception:
                msg = None
        if not msg:
            try:
                async for old in thread.history(limit=80):
                    if int(getattr(old.author, "id", 0)) != int(self.bot.user.id):
                        continue
                    if str(getattr(old, "content", "")) == marker:
                        msg = old
                        await self.db.set_parliament_party_thread_info_message(int(party["id"]), int(old.id))
                        break
            except Exception:
                pass
        if msg:
            try:
                await msg.edit(content=marker, embeds=[], view=view)
                return
            except Exception:
                try:
                    await self.db.set_parliament_party_logo(int(party["id"]), None)
                    refreshed = await self.db.get_parliament_party(int(party["id"]))
                    if refreshed:
                        fallback_view = await self._build_party_info_view(guild, refreshed)
                        await msg.edit(content=marker, embeds=[], view=fallback_view)
                        return
                except Exception:
                    return
        try:
            sent = await thread.send(content=marker, view=view)
        except Exception:
            try:
                await self.db.set_parliament_party_logo(int(party["id"]), None)
                refreshed = await self.db.get_parliament_party(int(party["id"]))
                if refreshed:
                    fallback_view = await self._build_party_info_view(guild, refreshed)
                    sent = await thread.send(content=marker, view=fallback_view)
                else:
                    return
            except Exception:
                return
        await self.db.set_parliament_party_thread_info_message(int(party["id"]), int(sent.id))
        try:
            async for old in thread.history(limit=80):
                if int(getattr(old.author, "id", 0)) != int(self.bot.user.id):
                    continue
                if int(old.id) == int(sent.id):
                    continue
                if str(getattr(old, "content", "")) == marker:
                    await old.delete()
                    continue
                if old.embeds and str(getattr(old.embeds[0], "title", "")).startswith("🏛️ Partei:"):
                    await old.delete()
        except Exception:
            pass

    async def create_party_panel(self, interaction: discord.Interaction):
        if not interaction.guild or not is_staff(self.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        target = interaction.channel
        if not isinstance(target, (discord.TextChannel, discord.Thread)):
            return await interaction.response.send_message("Nur in Textkanälen nutzbar.", ephemeral=True)
        from bot.modules.parlament.views.party_views import PartyCreatePanelView

        await target.send(view=PartyCreatePanelView())
        await interaction.response.send_message("Partei-Panel gesendet.", ephemeral=True)

    async def create_party_from_modal(self, interaction: discord.Interaction, name: str, description: str, member_ids_raw: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        candidate_role = self._get_role(interaction.guild, self._candidate_role_id(interaction.guild.id))
        if not candidate_role or candidate_role not in interaction.user.roles:
            return await interaction.response.send_message("Nur mit Parlamentskandidaten-Rolle möglich.", ephemeral=True)

        party_name = str(name or "").strip()
        if len(party_name) < 3:
            return await interaction.response.send_message("Parteiname ist zu kurz.", ephemeral=True)
        if len(party_name) > 50:
            return await interaction.response.send_message("Parteiname ist zu lang (max. 50).", ephemeral=True)

        existing = await self.db.get_parliament_party_for_user(interaction.guild.id, interaction.user.id)
        if existing:
            return await interaction.response.send_message("Du bist bereits in einer aktiven Partei.", ephemeral=True)

        slug = self._party_slug(party_name)
        duplicate = await self.db.get_parliament_party_by_slug(interaction.guild.id, slug)
        if duplicate and str(duplicate[5]) in {"pending", "approved"}:
            return await interaction.response.send_message("Dieser Parteiname ist bereits vergeben.", ephemeral=True)

        member_ids = {int(interaction.user.id)}
        for uid in self._extract_user_ids(member_ids_raw):
            if len(member_ids) >= 25:
                break
            member = interaction.guild.get_member(int(uid))
            if not member:
                continue
            already = await self.db.get_parliament_party_for_user(interaction.guild.id, int(uid))
            if already:
                continue
            member_ids.add(int(uid))
        if len(member_ids) < 3:
            return await interaction.response.send_message(
                "Für eine Partei sind mindestens 3 Mitglieder nötig (inkl. dir).",
                ephemeral=True,
            )

        request_channel = await self._get_request_channel(interaction.guild)
        if not request_channel:
            return await interaction.response.send_message("Partei-Request-Channel ist nicht konfiguriert.", ephemeral=True)

        party_id = await self.db.create_parliament_party(
            interaction.guild.id,
            party_name,
            slug,
            interaction.user.id,
            description=description,
            forum_thread_id=None,
        )

        await self.db.add_parliament_party_member(party_id, interaction.guild.id, interaction.user.id, "leader", added_by=interaction.user.id)
        for uid in member_ids:
            if uid == interaction.user.id:
                continue
            await self.db.add_parliament_party_member(party_id, interaction.guild.id, uid, "member", added_by=interaction.user.id)

        mentions = []
        for role_id in self._party_team_role_ids(interaction.guild.id):
            role = interaction.guild.get_role(role_id)
            if role:
                mentions.append(role.mention)
        mention_text = " ".join(mentions).strip()
        leader_mentions = []
        for uid in member_ids:
            member = interaction.guild.get_member(int(uid))
            if member:
                leader_mentions.append(member.mention)
        embed = discord.Embed(
            title=f"Neue Partei-Anfrage #{party_id}",
            description=str(description or "").strip()[:1000],
            color=0xB16B91,
        )
        embed.add_field(name="Partei", value=party_name, inline=True)
        embed.add_field(name="Gründer", value=interaction.user.mention, inline=True)
        embed.add_field(name="Mitglieder", value=str(len(member_ids)), inline=True)
        embed.add_field(name="Mitgliedsliste", value=", ".join(leader_mentions)[:1000] or "—", inline=False)
        head = f"{mention_text}\n" if mention_text else ""
        await request_channel.send(f"{head}Neue Partei-Anfrage eingegangen.", embed=embed)

        await interaction.response.send_message(
            f"Partei-Antrag erstellt: **#{party_id} {party_name}**. Das Team prüft jetzt eure Gründung.",
            ephemeral=True,
        )

    async def approve_party(self, interaction: discord.Interaction, party_id: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._send_ephemeral(interaction, "Nur im Server nutzbar.")
        if not is_staff(self.settings, interaction.user):
            return await self._send_ephemeral(interaction, "Keine Rechte.")
        if not interaction.response.is_done():
            try:
                await interaction.response.defer(ephemeral=True, thinking=True)
            except Exception:
                pass

        party_row = await self.db.get_parliament_party(int(party_id))
        if not party_row:
            return await self._send_ephemeral(interaction, "Partei nicht gefunden.")
        party = self._party_data(party_row)
        if int(party["guild_id"]) != int(interaction.guild.id):
            return await self._send_ephemeral(interaction, "Partei nicht gefunden.")
        if str(party["status"]) != "pending":
            return await self._send_ephemeral(interaction, "Partei ist nicht mehr im Status 'pending'.")

        members = await self.db.list_parliament_party_members(int(party["id"]))
        if len(members) < 3:
            return await self._send_ephemeral(interaction, "Genehmigung nicht möglich: mindestens 3 Mitglieder erforderlich.")

        member_ids = [int(r[2]) for r in members]
        leader_row = next((m for m in members if str(m[3]) == "leader"), None)
        leader_id = int(leader_row[2]) if leader_row else int(party["founder_id"])
        category_name = f"{self._party_category_prefix(interaction.guild.id)} • {party['name']}"[:95]
        party_role = await self._ensure_party_role(interaction.guild, party_row)
        refreshed_before_channels = await self.db.get_parliament_party(int(party["id"]))
        if refreshed_before_channels:
            party = self._party_data(refreshed_before_channels)
        overwrites = self._party_overwrites(interaction.guild, member_ids, party_role=party_role)
        category = await interaction.guild.create_category(name=category_name, overwrites=overwrites, reason=f"Partei genehmigt #{party_id}")
        panel_overwrites = self._party_panel_overwrites(interaction.guild, leader_id=leader_id, member_ids=member_ids, party_role=party_role)
        panel_channel = await interaction.guild.create_text_channel(name="🛠️・panel", category=category, overwrites=panel_overwrites, reason=f"Partei #{party_id}")
        text_channel = await interaction.guild.create_text_channel(name="💬・chat", category=category, reason=f"Partei #{party_id}")
        voice_channel = await interaction.guild.create_voice_channel(name="🔊・talk", category=category, reason=f"Partei #{party_id}")

        settings_msg = await panel_channel.send(view=PartySettingsPanelView(self.settings, interaction.guild))
        await text_channel.send(
            f"Willkommen im Parteikanal von **{party['name']}**.\n"
            f"Organisation und Verwaltung läuft in {panel_channel.mention}."
        )

        await self.db.set_parliament_party_channels(
            int(party["id"]),
            category_id=int(category.id),
            text_channel_id=int(text_channel.id),
            settings_channel_id=int(panel_channel.id),
            voice_channel_id=int(voice_channel.id),
            party_role_id=int(party_role.id) if party_role else None,
            settings_message_id=int(settings_msg.id),
        )
        await self.db.set_parliament_party_status_approved(int(party["id"]), int(interaction.user.id))
        refreshed_after = await self.db.get_parliament_party(int(party["id"]))
        if refreshed_after:
            await self._sync_party_role_members(interaction.guild, refreshed_after)

        forum = await self._get_forum_channel(interaction.guild)
        if forum:
            thread_result = await forum.create_thread(
                name=f"🏛️ {party['name']}"[:100],
                content=f"Öffentlicher Parteithread: **{party['name']}**",
            )
            thread = thread_result.thread
            await self.db.set_parliament_party_forum_thread(int(party["id"]), int(thread.id))
            refreshed = await self.db.get_parliament_party(int(party["id"]))
            if refreshed:
                await self._sync_party_info_message(interaction.guild, refreshed)
        await self._send_ephemeral(interaction, f"Partei **#{party_id} {party['name']}** wurde genehmigt.")

    async def reject_party(self, interaction: discord.Interaction, party_id: int, reason: str | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)

        party_row = await self.db.get_parliament_party(int(party_id))
        if not party_row:
            return await interaction.response.send_message("Partei nicht gefunden.", ephemeral=True)
        party = self._party_data(party_row)
        if int(party["guild_id"]) != int(interaction.guild.id):
            return await interaction.response.send_message("Partei nicht gefunden.", ephemeral=True)
        if str(party["status"]) != "pending":
            return await interaction.response.send_message("Partei ist nicht mehr im Status 'pending'.", ephemeral=True)

        await self.db.set_parliament_party_status_rejected(int(party["id"]), int(interaction.user.id), reason=reason)
        await interaction.response.send_message(f"Partei **#{party_id} {party['name']}** wurde abgelehnt.", ephemeral=True)

    async def list_parties(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        rows = await self.db.list_parliament_parties(interaction.guild.id, limit=100)
        if not rows:
            return await interaction.response.send_message("Keine Parteien vorhanden.", ephemeral=True)
        lines = []
        for row in rows[:20]:
            status = str(row[5])
            leader_id = int(row[4] or 0)
            member_rows = await self.db.list_parliament_party_members(int(row[0]))
            lines.append(
                f"**#{int(row[0])} {row[2]}** · `{status}` · Mitglieder: **{len(member_rows)}** · Leiter: <@{leader_id}>"
            )
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    async def _refresh_party_channels(self, guild: discord.Guild, party_row):
        party = self._party_data(party_row)
        category_id = int(party["category_id"] or 0)
        if not category_id:
            return
        party_role = guild.get_role(int(party["party_role_id"] or 0)) if party.get("party_role_id") else None
        category = guild.get_channel(category_id)
        if not isinstance(category, discord.CategoryChannel):
            try:
                fetched = await guild.fetch_channel(category_id)
            except Exception:
                fetched = None
            category = fetched if isinstance(fetched, discord.CategoryChannel) else None
        if not category:
            return
        members = await self.db.list_parliament_party_members(int(party["id"]))
        member_ids = [int(r[2]) for r in members]
        overwrites = self._party_overwrites(guild, member_ids, party_role=party_role)
        try:
            await category.edit(overwrites=overwrites)
        except Exception:
            pass
        panel_channel_id = int(party["settings_channel_id"] or 0)
        if panel_channel_id:
            panel_channel = guild.get_channel(panel_channel_id)
            if isinstance(panel_channel, discord.TextChannel):
                leader_row = next((m for m in members if str(m[3]) == "leader"), None)
                leader_id = int(leader_row[2]) if leader_row else int(party["founder_id"])
                try:
                    await panel_channel.edit(overwrites=self._party_panel_overwrites(guild, leader_id, member_ids, party_role=party_role))
                except Exception:
                    pass
                panel_message_id = int(party["settings_message_id"] or 0)
                if panel_message_id:
                    try:
                        msg = await panel_channel.fetch_message(panel_message_id)
                        await msg.edit(view=PartySettingsPanelView(self.settings, guild))
                    except Exception:
                        pass
        await self._sync_party_role_members(guild, party_row)

    async def update_party_logo(self, interaction: discord.Interaction, logo_url: str):
        party = await self._resolve_party_for_panel_interaction(interaction)
        if not party:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        value = str(logo_url or "").strip()
        if value and not self._is_http_url(value):
            return await interaction.response.send_message("Ungültige URL. Nutze http/https oder lade ein Bild im Panel-Channel mit `logo` hoch.", ephemeral=True)
        try:
            await self.db.set_parliament_party_logo(int(party[0]), value or None)
            refreshed = await self.db.get_parliament_party(int(party[0]))
            if refreshed and interaction.guild:
                await self._sync_party_info_message(interaction.guild, refreshed)
            await interaction.response.send_message("Logo gespeichert.", ephemeral=True)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message("Logo konnte nicht gespeichert werden.", ephemeral=True)
            else:
                await interaction.followup.send("Logo konnte nicht gespeichert werden.", ephemeral=True)

    async def clear_party_logo(self, interaction: discord.Interaction):
        party = await self._resolve_party_for_panel_interaction(interaction)
        if not party:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        await self.db.set_parliament_party_logo(int(party[0]), None)
        refreshed = await self.db.get_parliament_party(int(party[0]))
        if refreshed and interaction.guild:
            await self._sync_party_info_message(interaction.guild, refreshed)
        await interaction.response.send_message("Logo entfernt.", ephemeral=True)

    async def update_party_basic_info(self, interaction: discord.Interaction, name: str, description: str):
        party_row = await self._resolve_party_for_panel_interaction(interaction)
        if not party_row:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party_row):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        party = self._party_data(party_row)
        new_name = str(name or "").strip()
        new_desc = str(description or "").strip()
        if len(new_name) < 3 or len(new_name) > 50:
            return await interaction.response.send_message("Parteiname muss 3-50 Zeichen lang sein.", ephemeral=True)
        new_slug = self._party_slug(new_name)
        dupe = await self.db.get_parliament_party_by_slug(interaction.guild.id, new_slug) if interaction.guild else None
        if dupe and int(dupe[0]) != int(party["id"]) and str(dupe[5]) in {"pending", "approved"}:
            return await interaction.response.send_message("Der Name ist bereits vergeben.", ephemeral=True)
        await self.db.set_parliament_party_basic_info(int(party["id"]), new_name, new_slug, new_desc[:500] if new_desc else None)
        refreshed = await self.db.get_parliament_party(int(party["id"]))
        if refreshed and interaction.guild:
            await self._ensure_party_role(interaction.guild, refreshed)
            await self._refresh_party_channels(interaction.guild, refreshed)
            await self._sync_party_info_message(interaction.guild, refreshed)
        await interaction.response.send_message("Parteidaten aktualisiert.", ephemeral=True)

    async def transfer_party_leadership(self, interaction: discord.Interaction, user_id_raw: str):
        party_row = await self._resolve_party_for_panel_interaction(interaction)
        if not party_row:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party_row):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        try:
            new_leader_id = int(str(user_id_raw).strip())
        except Exception:
            return await interaction.response.send_message("Ungültige User-ID.", ephemeral=True)
        target_member = interaction.guild.get_member(new_leader_id)
        if not target_member:
            return await interaction.response.send_message("Mitglied nicht gefunden.", ephemeral=True)
        member_row = await self.db.get_parliament_party_member(int(party_row[0]), new_leader_id)
        if not member_row:
            return await interaction.response.send_message("User muss zuerst Mitglied der Partei sein.", ephemeral=True)
        current = await self.db.list_parliament_party_members(int(party_row[0]))
        current_leader = next((m for m in current if str(m[3]) == "leader"), None)
        if current_leader and int(current_leader[2]) == int(new_leader_id):
            return await interaction.response.send_message("User ist bereits Parteichef.", ephemeral=True)
        if current_leader:
            await self.db.add_parliament_party_member(int(party_row[0]), interaction.guild.id, int(current_leader[2]), "member", added_by=int(interaction.user.id))
        await self.db.add_parliament_party_member(int(party_row[0]), interaction.guild.id, int(new_leader_id), "leader", added_by=int(interaction.user.id))
        refreshed = await self.db.get_parliament_party(int(party_row[0]))
        if refreshed:
            await self._refresh_party_channels(interaction.guild, refreshed)
            await self._sync_party_info_message(interaction.guild, refreshed)
        await interaction.response.send_message(f"Parteichef ist jetzt {target_member.mention}.", ephemeral=True)

    async def sync_party_public_info(self, interaction: discord.Interaction):
        party_row = await self._resolve_party_for_panel_interaction(interaction)
        if not party_row:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party_row):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await self._sync_party_info_message(interaction.guild, party_row)
        await interaction.response.send_message("Öffentlicher Partei-Thread wurde aktualisiert.", ephemeral=True)

    async def refresh_party_presentations(self, guild: discord.Guild):
        rows = await self.db.list_parliament_parties(guild.id, status="approved", limit=300)
        for row in rows:
            try:
                await self._ensure_party_role(guild, row)
                await self._refresh_party_channels(guild, row)
                await self._sync_party_info_message(guild, row)
                party = self._party_data(row)
                panel_channel_id = int(party["settings_channel_id"] or 0)
                panel_message_id = int(party["settings_message_id"] or 0)
                if panel_channel_id and panel_message_id:
                    panel_channel = guild.get_channel(panel_channel_id)
                    if isinstance(panel_channel, discord.TextChannel):
                        try:
                            msg = await panel_channel.fetch_message(panel_message_id)
                            await msg.edit(view=PartySettingsPanelView(self.settings, guild))
                        except Exception:
                            pass
            except Exception:
                continue

    async def submit_party_program(self, interaction: discord.Interaction, program_text: str):
        party = await self._resolve_party_for_panel_interaction(interaction)
        if not party:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        text = str(program_text or "").strip()
        if len(text) < 20:
            return await interaction.response.send_message("Programm ist zu kurz.", ephemeral=True)

        existing_attachments_json = str(party[9] or "").strip() or None
        await self.db.set_parliament_party_manifesto(int(party[0]), text[:4000], attachments_json=existing_attachments_json)
        thread_id = int(party[10] or 0)
        if not interaction.guild or not thread_id:
            return await interaction.response.send_message("Parteithread ist nicht konfiguriert.", ephemeral=True)
        thread = await self._get_party_thread(interaction.guild, thread_id)
        if not thread:
            return await interaction.response.send_message("Parteithread nicht gefunden.", ephemeral=True)
        try:
            await thread.edit(archived=False, locked=False)
        except Exception:
            pass
        if isinstance(interaction.user, discord.Member):
            try:
                await thread.add_user(interaction.user)
            except Exception:
                pass
        await thread.send(
            f"📜 **Parteiprogramm von {interaction.user.mention}**\n\n{text[:3900]}"
        )
        refreshed = await self.db.get_parliament_party(int(party[0]))
        if refreshed:
            await self._sync_party_info_message(interaction.guild, refreshed)
        await interaction.response.send_message(f"Programm im Thread {thread.mention} eingereicht.", ephemeral=True)

    async def submit_party_program_from_message(self, message: discord.Message):
        if not message.guild or not isinstance(message.author, discord.Member):
            return
        party_row = await self.db.get_parliament_party_by_settings_channel(message.guild.id, int(message.channel.id))
        if not party_row:
            return
        member_row = await self.db.get_parliament_party_member(int(party_row[0]), int(message.author.id))
        if not member_row or str(member_row[3]) != "leader":
            return
        text = str(message.content or "").strip()
        lower = text.lower()
        if lower in {"logo", "setlogo", "logo setzen"} or lower.startswith("logo "):
            image_url = self._extract_first_image_attachment_url(message)
            if not image_url:
                try:
                    await message.reply("Bitte hänge ein Bild an, um das Logo zu setzen.", mention_author=False)
                except Exception:
                    pass
                return
            await self.db.set_parliament_party_logo(int(party_row[0]), image_url)
            refreshed = await self.db.get_parliament_party(int(party_row[0]))
            if refreshed:
                await self._sync_party_info_message(message.guild, refreshed)
            try:
                await message.reply("Logo wurde gesetzt.", mention_author=False)
            except Exception:
                pass
            return
        attachment_urls = []
        for a in list(getattr(message, "attachments", []) or []):
            url = str(getattr(a, "url", "") or "").strip()
            if url:
                attachment_urls.append(url)
        if not text and not attachment_urls:
            return
        attachments_json = json.dumps(attachment_urls, ensure_ascii=False) if attachment_urls else None
        await self.db.set_parliament_party_manifesto(int(party_row[0]), text[:4000] if text else None, attachments_json=attachments_json)
        party = self._party_data(party_row)
        thread_id = int(party["forum_thread_id"] or 0)
        thread = await self._get_party_thread(message.guild, thread_id) if thread_id else None
        if thread:
            lines = [f"📜 **Programm-Update von {message.author.mention}**"]
            if text:
                lines.append(text[:3800])
            if attachment_urls:
                lines.append("**Anhänge**")
                lines.extend(attachment_urls[:8])
            await thread.send("\n\n".join(lines))
        refreshed = await self.db.get_parliament_party(int(party_row[0]))
        if refreshed:
            await self._sync_party_info_message(message.guild, refreshed)

    async def add_party_member_from_panel(self, interaction: discord.Interaction, user_id_raw: str):
        party = await self._resolve_party_for_panel_interaction(interaction)
        if not party:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        try:
            user_id = int(str(user_id_raw).strip())
        except Exception:
            return await interaction.response.send_message("Ungültige User-ID.", ephemeral=True)
        member = interaction.guild.get_member(user_id)
        if not member:
            return await interaction.response.send_message("Mitglied nicht gefunden.", ephemeral=True)
        active_party = await self.db.get_parliament_party_for_user(interaction.guild.id, user_id)
        if active_party and int(active_party[0]) != int(party[0]):
            return await interaction.response.send_message("User ist bereits in einer aktiven Partei.", ephemeral=True)

        await self.db.add_parliament_party_member(int(party[0]), interaction.guild.id, user_id, "member", added_by=int(interaction.user.id))
        await self._refresh_party_channels(interaction.guild, party)
        await interaction.response.send_message(f"{member.mention} wurde hinzugefügt.", ephemeral=True)

    async def remove_party_member_from_panel(self, interaction: discord.Interaction, user_id_raw: str):
        party = await self._resolve_party_for_panel_interaction(interaction)
        if not party:
            return await interaction.response.send_message("Dieser Kanal ist keinem Partei-Panel zugeordnet.", ephemeral=True)
        if not await self._is_party_leader(interaction, party):
            return await interaction.response.send_message("Nur der Parteichef darf das.", ephemeral=True)
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        try:
            user_id = int(str(user_id_raw).strip())
        except Exception:
            return await interaction.response.send_message("Ungültige User-ID.", ephemeral=True)
        member_row = await self.db.get_parliament_party_member(int(party[0]), user_id)
        if not member_row:
            return await interaction.response.send_message("User ist nicht in dieser Partei.", ephemeral=True)
        if str(member_row[3]) == "leader":
            return await interaction.response.send_message("Parteileitung kann nicht entfernt werden.", ephemeral=True)

        await self.db.remove_parliament_party_member(int(party[0]), user_id)
        await self._refresh_party_channels(interaction.guild, party)
        await interaction.response.send_message(f"User <@{user_id}> wurde entfernt.", ephemeral=True)

    async def refresh_all_panels(self):
        for guild in list(self.bot.guilds):
            try:
                await self.update_panel(guild)
            except Exception:
                continue
            try:
                await self.refresh_party_presentations(guild)
            except Exception:
                continue

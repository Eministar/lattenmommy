from __future__ import annotations

import json
from datetime import datetime, timezone
import discord

from bot.core.perms import is_staff
from bot.modules.parlament.formatting.parlament_embeds import (
    build_parliament_panel_embed,
    build_parliament_vote_container,
)
from bot.modules.parlament.views.vote_view import ParliamentVoteView


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

    async def refresh_all_panels(self):
        for guild in list(self.bot.guilds):
            try:
                await self.update_panel(guild)
            except Exception:
                continue

import json
from datetime import datetime, timezone
import discord
from bot.utils.emojis import em
from bot.utils.assets import Banners


class PollService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _color(self, guild: discord.Guild | None) -> int:
        gid = guild.id if guild else 0
        v = str(self.settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
        try:
            return int(v, 16)
        except Exception:
            return 0xB16B91

    def _bar(self, pct: int) -> str:
        full = "█" * max(1, int(pct / 10))
        empty = "░" * (10 - len(full))
        return f"`{full}{empty}` {pct}%"

    async def create_poll(self, guild: discord.Guild, channel: discord.TextChannel, question: str, options: list[str], created_by: int):
        poll_id = await self.db.create_poll(guild.id, channel.id, question, json.dumps(options, ensure_ascii=False), created_by)
        view = await self.build_poll_view(guild, poll_id, options)
        msg = await channel.send(view=view)
        await self.db.set_poll_message(poll_id, msg.id)
        return poll_id

    async def build_poll_embed(self, guild: discord.Guild, poll_id: int):
        return await self.build_poll_view(guild, poll_id)

    async def build_poll_view(self, guild: discord.Guild, poll_id: int, options: list[str] | None = None):
        row = await self.db.get_poll(poll_id)
        if not row:
            return None
        _, _, _, _, question, options_json, _, status, created_at = row
        options = options or json.loads(options_json)
        votes = await self.db.list_poll_votes(poll_id)
        total = max(1, len(votes))
        counts = [0 for _ in options]
        for idx in votes:
            if 0 <= idx < len(counts):
                counts[idx] += 1

        arrow2 = em(self.settings, "arrow2", guild) or "»"
        info = em(self.settings, "info", guild) or "ℹ️"
        status_label = "OFFEN" if status == "open" else "GESCHLOSSEN"

        lines = []
        for i, opt in enumerate(options):
            pct = int((counts[i] / total) * 100) if total else 0
            lines.append(f"**{i+1}. {opt}**\n{self._bar(pct)} • {counts[i]} Stimme(n)")
        desc = f"{arrow2} {question}\n\n" + "\n\n".join(lines)

        container = discord.ui.Container(accent_colour=self._color(guild))
        try:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=Banners.POLL)
            container.add_item(gallery)
            container.add_item(discord.ui.Separator())
        except Exception:
            pass
        container.add_item(discord.ui.TextDisplay(f"**{info} 𑁉 UMFRAGE • {status_label}**"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(desc))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"ID {poll_id} • {created_at}"))

        return PollView(self, poll_id, options, container=container)

    async def vote(self, interaction: discord.Interaction, poll_id: int, option_index: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        row = await self.db.get_poll(poll_id)
        if not row:
            return await interaction.response.send_message("Umfrage nicht gefunden.", ephemeral=True)
        status = str(row[7])
        if status != "open":
            return await interaction.response.send_message("Umfrage ist geschlossen.", ephemeral=True)
        await self.db.add_poll_vote(poll_id, interaction.user.id, int(option_index))
        try:
            view = await self.build_poll_view(interaction.guild, poll_id)
            if view:
                await interaction.message.edit(view=view)
        except Exception:
            pass
        await interaction.response.send_message("Stimme gespeichert.", ephemeral=True)

    async def restore_views(self):
        rows = await self.db.list_open_polls()
        for row in rows:
            try:
                poll_id, guild_id, channel_id, message_id, options_json = row
            except Exception:
                continue
            if not message_id:
                continue
            try:
                options = json.loads(options_json)
            except Exception:
                continue
            custom_id = None
            try:
                guild = self.bot.get_guild(int(guild_id))
                channel = None
                if guild:
                    channel = guild.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))
                if channel:
                    msg = await channel.fetch_message(int(message_id))
                    for row in getattr(msg, "components", []) or []:
                        for child in getattr(row, "children", []) or []:
                            cid = getattr(child, "custom_id", None)
                            if cid:
                                custom_id = str(cid)
                                break
                        if custom_id:
                            break
            except Exception:
                custom_id = None
            try:
                view = PollView(self, int(poll_id), options, custom_id=custom_id)
                self.bot.add_view(view, message_id=int(message_id))
            except Exception:
                pass


class PollSelect(discord.ui.Select):
    def __init__(self, service: PollService, poll_id: int, options: list[str], custom_id: str | None = None):
        self.service = service
        self.poll_id = int(poll_id)
        opts = [
            discord.SelectOption(label=opt[:100], value=str(i))
            for i, opt in enumerate(options)
        ]
        super().__init__(
            placeholder="Option wählen…",
            options=opts[:25],
            min_values=1,
            max_values=1,
            custom_id=custom_id or f"starry:poll:{self.poll_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            idx = int(self.values[0])
        except Exception:
            return await interaction.response.send_message("Ungültige Auswahl.", ephemeral=True)
        await self.service.vote(interaction, self.poll_id, idx)


class PollView(discord.ui.LayoutView):
    def __init__(
        self,
        service: PollService,
        poll_id: int,
        options: list[str],
        custom_id: str | None = None,
        container: discord.ui.Container | None = None,
    ):
        super().__init__(timeout=None)
        if container:
            self.add_item(container)
        row = discord.ui.ActionRow()
        row.add_item(PollSelect(service, poll_id, options, custom_id=custom_id))
        self.add_item(row)

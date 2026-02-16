import json
import re
from datetime import datetime, timezone, timedelta
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
        full = "█" * min(10, max(0, int(round(pct / 10))))
        empty = "░" * (10 - len(full))
        return f"`{full}{empty}` {pct}%"

    def _parse_duration(self, raw: str | None) -> int | None:
        s = str(raw or "").strip().lower()
        if not s:
            return None
        m = re.match(r"^(\d+)\s*([mhd])$", s)
        if not m:
            return None
        value = int(m.group(1))
        unit = m.group(2)
        if value <= 0:
            return None
        if unit == "m":
            return value
        if unit == "h":
            return value * 60
        return value * 1440

    def _safe_emoji_text(self, value: str | None) -> str | None:
        token = str(value or "").strip()
        if not token:
            return None
        return token[:64]

    def _normalize_options(self, raw_options: list[str] | list[dict]) -> list[dict]:
        normalized: list[dict] = []
        for item in raw_options:
            if isinstance(item, dict):
                label = str(item.get("label") or "").strip()
                emoji = self._safe_emoji_text(item.get("emoji"))
            else:
                label = str(item).strip()
                emoji = None
            if not label:
                continue
            normalized.append({"label": label[:100], "emoji": emoji})
        return normalized

    def _select_emoji(self, raw: str | None):
        token = str(raw or "").strip()
        if not token:
            return None
        if token.startswith("<") and token.endswith(">"):
            try:
                return discord.PartialEmoji.from_str(token)
            except Exception:
                return None
        return token

    def _format_ts(self, iso_value: str | None, style: str = "R") -> str | None:
        if not iso_value:
            return None
        try:
            dt = datetime.fromisoformat(str(iso_value))
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return f"<t:{int(dt.timestamp())}:{style}>"

    async def create_poll(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        question: str,
        options: list[str] | list[dict],
        created_by: int,
        duration_minutes: int | None = None,
        image_url: str | None = None,
    ):
        option_data = self._normalize_options(options)
        end_at = None
        if duration_minutes and duration_minutes > 0:
            end_at = (datetime.now(timezone.utc) + timedelta(minutes=int(duration_minutes))).isoformat()
        poll_id = await self.db.create_poll(
            guild.id,
            channel.id,
            question,
            json.dumps(option_data, ensure_ascii=False),
            created_by,
            end_at=end_at,
            image_url=image_url,
        )
        view = await self.build_poll_view(guild, poll_id, option_data)
        msg = await channel.send(view=view)
        await self.db.set_poll_message(poll_id, msg.id)
        return poll_id

    async def build_poll_embed(self, guild: discord.Guild | None, poll_id: int):
        return await self.build_poll_view(guild, poll_id)

    async def build_poll_view(
        self,
        guild: discord.Guild | None,
        poll_id: int,
        options: list[str] | list[dict] | None = None,
    ):
        row = await self.db.get_poll(poll_id)
        if not row:
            return None
        _, _, _, _, question, options_json, image_url, end_at, created_by, status, created_at, _ = row
        try:
            loaded_options = json.loads(options_json)
        except Exception:
            loaded_options = []
        options = self._normalize_options(options or loaded_options)
        if not options:
            return None
        votes = await self.db.list_poll_votes(poll_id)
        total_votes = len(votes)
        counts = [0 for _ in options]
        for idx in votes:
            if 0 <= idx < len(counts):
                counts[idx] += 1

        arrow2 = em(self.settings, "arrow2", guild) or "»"
        info = em(self.settings, "info", guild) or "ℹ️"
        status_label = "OFFEN" if status == "open" else "GESCHLOSSEN"
        created_rel = self._format_ts(created_at, "R") or str(created_at)
        end_rel = self._format_ts(end_at, "R")
        end_abs = self._format_ts(end_at, "f")
        creator_text = f"<@{int(created_by)}>" if created_by else "—"

        lines = []
        for i, opt in enumerate(options):
            label = str(opt.get("label") or "Option")
            icon = str(opt.get("emoji") or "").strip()
            shown = f"{icon} {label}".strip()
            pct = int((counts[i] / max(1, total_votes)) * 100) if total_votes else 0
            lines.append(f"**{i + 1}. {shown}**\n{self._bar(pct)} • {counts[i]} Stimme(n)")
        desc = f"{arrow2} {question}\n\n" + "\n\n".join(lines)
        details = [
            f"ID {poll_id}",
            f"Erstellt: {created_rel}",
            f"Von: {creator_text}",
            f"Stimmen gesamt: **{total_votes}**",
        ]
        if end_rel and end_abs:
            details.append(f"Endet: {end_rel} ({end_abs})")
        if status != "open":
            details.append("Status: Beendet")

        container = discord.ui.Container(accent_colour=self._color(guild))
        try:
            gallery = discord.ui.MediaGallery()
            if image_url:
                gallery.add_item(media=str(image_url))
            gallery.add_item(media=Banners.POLL)
            container.add_item(gallery)
            container.add_item(discord.ui.Separator())
        except Exception:
            pass
        container.add_item(discord.ui.TextDisplay(f"**{info} 𑁉 UMFRAGE • {status_label}**"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(desc))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(" • ".join(details)))

        return PollView(self, poll_id, options, container=container, disabled=str(status) != "open")

    async def vote(self, interaction: discord.Interaction, poll_id: int, option_index: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        row = await self.db.get_poll(poll_id)
        if not row:
            return await interaction.response.send_message("Umfrage nicht gefunden.", ephemeral=True)
        status = str(row[9])
        if status != "open":
            return await interaction.response.send_message("Umfrage ist geschlossen.", ephemeral=True)
        try:
            option_data = self._normalize_options(json.loads(row[5]))
        except Exception:
            option_data = []
        if option_index < 0 or option_index >= len(option_data):
            return await interaction.response.send_message("Ungültige Auswahl.", ephemeral=True)
        await self.db.add_poll_vote(poll_id, interaction.user.id, int(option_index))
        try:
            view = await self.build_poll_view(interaction.guild, poll_id)
            if view:
                await interaction.message.edit(view=view)
        except Exception:
            pass
        picked = option_data[option_index]
        icon = str(picked.get("emoji") or "").strip()
        label = str(picked.get("label") or "Option")
        shown = f"{icon} {label}".strip()
        await interaction.response.send_message(f"Stimme gespeichert: **{shown}**", ephemeral=True)

    async def tick(self):
        now = datetime.now(timezone.utc)
        rows = await self.db.list_open_polls()
        for row in rows:
            try:
                poll_id, guild_id, channel_id, message_id, _, end_at = row
            except Exception:
                continue
            if not end_at:
                continue
            try:
                end_dt = datetime.fromisoformat(str(end_at))
            except Exception:
                continue
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)
            if end_dt > now:
                continue
            guild = self.bot.get_guild(int(guild_id))
            if not guild:
                try:
                    guild = await self.bot.fetch_guild(int(guild_id))
                except Exception:
                    guild = None
            if guild and not self.settings.get_guild_bool(guild.id, "poll.enabled", True):
                continue
            await self._finish_poll(guild, int(poll_id), int(channel_id), int(message_id or 0), reason="auto")

    async def close_poll(self, guild: discord.Guild, poll_id: int):
        row = await self.db.get_poll(poll_id)
        if not row:
            return False, "poll_not_found"
        if int(row[1]) != int(guild.id):
            return False, "poll_other_guild"
        if str(row[9]) != "open":
            return False, "poll_already_closed"
        await self._finish_poll(guild, int(row[0]), int(row[2]), int(row[3] or 0), reason="manual")
        return True, None

    async def _finish_poll(
        self,
        guild: discord.Guild | None,
        poll_id: int,
        channel_id: int,
        message_id: int,
        reason: str = "auto",
    ):
        await self.db.close_poll(poll_id)
        row = await self.db.get_poll(poll_id)
        if not row:
            return
        question = str(row[4] or "Umfrage")
        try:
            options = self._normalize_options(json.loads(row[5]))
        except Exception:
            options = []
        votes = await self.db.list_poll_votes(poll_id)
        counts = [0 for _ in options]
        for idx in votes:
            if 0 <= idx < len(counts):
                counts[idx] += 1
        winner_text = "—"
        if counts:
            max_votes = max(counts)
            if max_votes > 0:
                best = []
                for i, c in enumerate(counts):
                    if c != max_votes:
                        continue
                    icon = str(options[i].get("emoji") or "").strip()
                    label = str(options[i].get("label") or "Option")
                    shown = f"{icon} {label}".strip()
                    best.append(shown)
                winner_text = ", ".join(best[:3])

        channel = None
        if guild:
            channel = guild.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                channel = None

        cheers = em(self.settings, "cheers", guild) or "🎉"
        cause = "automatisch" if reason == "auto" else "manuell"
        result_text = (
            f"{cheers} **Umfrage beendet ({cause})**\n"
            f"Frage: **{question}**\n"
            f"Top-Option: **{winner_text}**\n"
            f"Gesamtstimmen: **{len(votes)}**"
        )
        if channel and isinstance(channel, discord.abc.Messageable):
            try:
                await channel.send(result_text)
            except Exception:
                pass
            if message_id:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    view = await self.build_poll_view(guild, poll_id)
                    if view:
                        await msg.edit(view=view)
                except Exception:
                    pass

    async def restore_views(self):
        rows = await self.db.list_open_polls()
        for row in rows:
            try:
                poll_id, guild_id, channel_id, message_id, options_json, _ = row
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
                view = PollView(self, int(poll_id), self._normalize_options(options), custom_id=custom_id)
                self.bot.add_view(view, message_id=int(message_id))
            except Exception:
                pass


class PollSelect(discord.ui.Select):
    def __init__(self, service: PollService, poll_id: int, options: list[dict], custom_id: str | None = None, disabled: bool = False):
        self.service = service
        self.poll_id = int(poll_id)
        opts = []
        for i, opt in enumerate(options):
            label = str(opt.get("label") or "Option")[:100]
            emoji_value = service._select_emoji(opt.get("emoji"))
            opts.append(discord.SelectOption(label=label, value=str(i), emoji=emoji_value))
        super().__init__(
            placeholder="Option wählen…",
            options=opts[:25],
            min_values=1,
            max_values=1,
            custom_id=custom_id or f"starry:poll:{self.poll_id}",
            disabled=disabled,
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
        options: list[dict],
        custom_id: str | None = None,
        container: discord.ui.Container | None = None,
        disabled: bool = False,
    ):
        super().__init__(timeout=None)
        if container:
            self.add_item(container)
        row = discord.ui.ActionRow()
        row.add_item(PollSelect(service, poll_id, options, custom_id=custom_id, disabled=disabled))
        self.add_item(row)

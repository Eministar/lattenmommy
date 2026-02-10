import json
import random
import re
from datetime import datetime, timezone, timedelta
import discord
from bot.utils.emojis import em
from bot.modules.giveaways.formatting.giveaway_views import build_confirm_container, build_giveaway_container


class GiveawayService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._pending = {}

    def _color(self, guild: discord.Guild | None) -> int:
        gid = guild.id if guild else 0
        v = str(self.settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
        try:
            return int(v, 16)
        except Exception:
            return 0xB16B91

    def _join_emoji(self, guild: discord.Guild | None) -> str:
        gid = guild.id if guild else 0
        token = str(self.settings.get_guild(gid, "giveaway.join_emoji", "🎉") or "🎉").strip()
        if token.startswith("<") and token.endswith(">"):
            return token
        key = token[1:-1] if token.startswith(":") and token.endswith(":") else token
        resolved = em(self.settings, key, guild)
        return resolved if resolved else token

    def _parse_duration(self, raw: str) -> int | None:
        s = str(raw or "").strip().lower()
        if not s:
            return None
        m = re.match(r"^(\d+)\s*([mhd])?$", s)
        if not m:
            return None
        val = int(m.group(1))
        unit = m.group(2) or "m"
        if unit == "m":
            return val
        if unit == "h":
            return val * 60
        if unit == "d":
            return val * 1440
        return None

    def _format_conditions(self, conditions: dict, guild: discord.Guild | None) -> str:
        lines = []
        if conditions.get("require_booster"):
            lines.append("• Server Booster")
        if conditions.get("require_no_boost"):
            lines.append("• Kein Booster")
        min_level = int(conditions.get("min_level") or 0)
        if min_level:
            lines.append(f"• Level {min_level}+")
        min_messages = int(conditions.get("min_messages") or 0)
        if min_messages:
            lines.append(f"• {min_messages} Nachrichten")
        min_voice_hours = int(conditions.get("min_voice_hours") or 0)
        if min_voice_hours:
            lines.append(f"• {min_voice_hours} Voice-Stunden")
        min_days = int(conditions.get("min_days") or 0)
        if min_days:
            lines.append(f"• {min_days} Tage auf dem Server")
        min_tickets = int(conditions.get("min_tickets") or 0)
        if min_tickets:
            lines.append(f"• {min_tickets} Tickets")
        min_account_days = int(conditions.get("min_account_days") or 0)
        if min_account_days:
            lines.append(f"• Account {min_account_days} Tage alt")
        required_role_id = int(conditions.get("required_role_id") or 0)
        if required_role_id:
            lines.append(f"• Rolle <@&{required_role_id}> erforderlich")
        excluded_role_id = int(conditions.get("excluded_role_id") or 0)
        if excluded_role_id:
            lines.append(f"• Rolle <@&{excluded_role_id}> ausgeschlossen")
        return "\n".join(lines) if lines else "—"

    async def _eligible(self, member: discord.Member, conditions: dict) -> tuple[bool, str | None]:
        if conditions.get("require_booster") and not member.premium_since:
            return False, "Nur Server Booster dürfen teilnehmen."
        if conditions.get("require_no_boost") and member.premium_since:
            return False, "Booster sind ausgeschlossen."
        required_role_id = int(conditions.get("required_role_id") or 0)
        if required_role_id:
            role = member.guild.get_role(required_role_id)
            if role and role not in member.roles:
                return False, "Benötigte Rolle fehlt."
        excluded_role_id = int(conditions.get("excluded_role_id") or 0)
        if excluded_role_id:
            role = member.guild.get_role(excluded_role_id)
            if role and role in member.roles:
                return False, "Ausgeschlossene Rolle vorhanden."
        min_days = int(conditions.get("min_days") or 0)
        if min_days and member.joined_at:
            days = int((datetime.now(timezone.utc) - member.joined_at).total_seconds() // 86400)
            if days < min_days:
                return False, f"Mindestens {min_days} Tage auf dem Server."
        min_account_days = int(conditions.get("min_account_days") or 0)
        if min_account_days:
            days = int((datetime.now(timezone.utc) - member.created_at).total_seconds() // 86400)
            if days < min_account_days:
                return False, f"Account muss {min_account_days} Tage alt sein."
        min_messages = int(conditions.get("min_messages") or 0)
        if min_messages:
            row = await self.db.get_user_stats(member.guild.id, member.id)
            if not row:
                return False, f"Mindestens {min_messages} Nachrichten."
            msg_count = int(row[2])
            if msg_count < min_messages:
                return False, f"Mindestens {min_messages} Nachrichten."
        min_level = int(conditions.get("min_level") or 0)
        if min_level:
            row = await self.db.get_user_stats(member.guild.id, member.id)
            if not row:
                return False, f"Mindestens Level {min_level}."
            level = int(row[6])
            if level < min_level:
                return False, f"Mindestens Level {min_level}."
        min_voice_hours = int(conditions.get("min_voice_hours") or 0)
        if min_voice_hours:
            row = await self.db.get_user_stats(member.guild.id, member.id)
            if not row:
                return False, f"Mindestens {min_voice_hours} Voice-Stunden."
            voice_hours = int(row[3]) // 3600
            if voice_hours < min_voice_hours:
                return False, f"Mindestens {min_voice_hours} Voice-Stunden."
        min_tickets = int(conditions.get("min_tickets") or 0)
        if min_tickets:
            tickets = await self.db.get_ticket_count(member.id)
            if tickets < min_tickets:
                return False, f"Mindestens {min_tickets} Tickets."
        return True, None

    async def create_giveaway(self, guild: discord.Guild, channel: discord.TextChannel, data: dict, conditions: dict):
        end_at = datetime.now(timezone.utc) + timedelta(minutes=int(data["duration_minutes"]))
        giveaway_id = await self.db.create_giveaway(
            guild_id=guild.id,
            channel_id=channel.id,
            title=data["title"],
            sponsor=data.get("sponsor"),
            description=data.get("description"),
            end_at=end_at.isoformat(),
            winner_count=int(data["winner_count"]),
            conditions_json=json.dumps(conditions, ensure_ascii=False),
            created_by=int(data["created_by"]),
        )

        view = await self.build_giveaway_view(guild, giveaway_id)
        msg = await channel.send(view=view)
        try:
            await msg.add_reaction(self._join_emoji(guild))
        except Exception:
            pass
        await self.db.set_giveaway_message(giveaway_id, msg.id)
        return giveaway_id

    async def build_confirm_embed(self, guild: discord.Guild, data: dict, conditions: dict):
        conditions_text = self._format_conditions(conditions, guild)
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            build_confirm_container(self.settings, guild, data, conditions_text, self._join_emoji(guild))
        )
        return view

    async def build_giveaway_embed(self, guild: discord.Guild, giveaway_id: int):
        return await self.build_giveaway_view(guild, giveaway_id)

    async def build_giveaway_view(self, guild: discord.Guild, giveaway_id: int):
        row = await self.db.get_giveaway(giveaway_id)
        if not row:
            return None
        _, _, _, _, title, sponsor, description, end_at, winners, conditions_json, _, status, _ = row
        conditions = json.loads(conditions_json) if conditions_json else {}
        entries = await self.db.count_giveaway_entries(giveaway_id)
        try:
            end_dt = datetime.fromisoformat(str(end_at))
        except Exception:
            end_dt = None
        data = {
            "title": title,
            "sponsor": sponsor,
            "description": description,
            "end_at": end_dt,
            "winners": winners,
            "entries": entries,
            "conditions": self._format_conditions(conditions, guild),
            "status": status,
        }
        join_button = GiveawayJoinButton(self, giveaway_id, disabled=str(status) != "open", emoji=self._join_emoji(guild))
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(build_giveaway_container(self.settings, guild, data, join_button))
        return view

    async def handle_join(self, interaction: discord.Interaction, giveaway_id: int):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        row = await self.db.get_giveaway(giveaway_id)
        if not row:
            return await interaction.response.send_message("Giveaway nicht gefunden.", ephemeral=True)
        status = str(row[11])
        if status != "open":
            return await interaction.response.send_message("Giveaway ist beendet.", ephemeral=True)
        conditions = json.loads(row[9]) if row[9] else {}
        ok, err = await self._eligible(interaction.user, conditions)
        if not ok:
            return await interaction.response.send_message(err or "Nicht berechtigt.", ephemeral=True)
        await self.db.add_giveaway_entry(giveaway_id, interaction.user.id)
        try:
            view = await self.build_giveaway_view(interaction.guild, giveaway_id)
            await interaction.message.edit(view=view)
        except Exception:
            pass
        await interaction.response.send_message("Du bist dabei! 🎉", ephemeral=True)

    async def tick(self):
        now = datetime.now(timezone.utc)
        for guild in list(self.bot.guilds):
            if not self.settings.get_guild_bool(guild.id, "giveaway.enabled", True):
                continue
            rows = await self.db.list_open_giveaways(guild.id)
            for row in rows:
                giveaway_id, channel_id, message_id, end_at = row
                try:
                    end_dt = datetime.fromisoformat(str(end_at))
                except Exception:
                    continue
                if end_dt > now:
                    continue
                await self._finish_giveaway(guild, int(giveaway_id), int(channel_id), int(message_id or 0))

    async def _finish_giveaway(self, guild: discord.Guild, giveaway_id: int, channel_id: int, message_id: int):
        await self.db.close_giveaway(giveaway_id)
        entries = await self.db.list_giveaway_entries(giveaway_id)
        row = await self.db.get_giveaway(giveaway_id)
        if not row:
            return
        _, _, _, _, title, sponsor, _, _, winners, _, _, _, _ = row
        winners = max(1, int(winners))
        picked = random.sample(entries, k=min(winners, len(entries))) if entries else []

        ch = guild.get_channel(channel_id)
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return

        cheers = em(self.settings, "cheers", guild) or "🎉"
        hearts = em(self.settings, "hearts", guild) or "💖"
        if picked:
            mentions = ", ".join([f"<@{uid}>" for uid in picked])
            text = f"{cheers} **Giveaway beendet!**\n{hearts} Gewinner: {mentions}\nPreis: **{title}**"
        else:
            text = f"{cheers} **Giveaway beendet!**\nKeine gültigen Teilnehmer.\nPreis: **{title}**"
        try:
            await ch.send(text)
        except Exception:
            pass

        if message_id:
            try:
                msg = await ch.fetch_message(int(message_id))
                view = await self.build_giveaway_view(guild, giveaway_id)
                if view:
                    await msg.edit(view=view)
            except Exception:
                pass

    async def reroll(self, guild: discord.Guild, giveaway_id: int):
        row = await self.db.get_giveaway(giveaway_id)
        if not row:
            return False, "giveaway_not_found"
        _, _, channel_id, message_id, title, _, _, _, winners, _, _, status, _ = row
        entries = await self.db.list_giveaway_entries(giveaway_id)
        if not entries:
            return False, "no_entries"
        winners = max(1, int(winners))
        picked = random.sample(entries, k=min(winners, len(entries)))
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return False, "channel_missing"
        cheers = em(self.settings, "cheers", guild) or "🎉"
        text = f"{cheers} **Reroll!**\nNeue Gewinner: " + ", ".join([f"<@{uid}>" for uid in picked])
        try:
            await ch.send(text)
        except Exception:
            pass
        if message_id:
            try:
                msg = await ch.fetch_message(int(message_id))
                view = await self.build_giveaway_view(guild, giveaway_id)
                if view:
                    await msg.edit(view=view)
            except Exception:
                pass
        return True, None


class GiveawayJoinButton(discord.ui.Button):
    def __init__(self, service: GiveawayService, giveaway_id: int, disabled: bool = False, emoji: str | None = None):
        super().__init__(
            label="Teilnehmen",
            style=discord.ButtonStyle.success,
            custom_id=f"giveaway_join_{int(giveaway_id)}",
            disabled=disabled,
            emoji=str(emoji) if emoji else None,
        )
        self.service = service
        self.giveaway_id = int(giveaway_id)

    async def callback(self, interaction: discord.Interaction):
        await self.service.handle_join(interaction, self.giveaway_id)

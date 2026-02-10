import discord
from discord import app_commands
from discord.ext import commands
from bot.modules.giveaways.services.giveaway_service import GiveawayService


class GiveawayCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "giveaway_service", None) or GiveawayService(bot, bot.settings, bot.db, bot.logger)

    giveaway = app_commands.Group(name="giveaway", description="🎁 𑁉 Giveaway-Tools")

    @giveaway.command(name="create", description="🎉 𑁉 Giveaway erstellen")
    @app_commands.describe(channel="Zielkanal", winners="Anzahl Gewinner")
    async def create(self, interaction: discord.Interaction, channel: discord.TextChannel, winners: int):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await interaction.response.send_modal(GiveawayCreateModal(self.service, channel.id, int(winners)))

    @giveaway.command(name="reroll", description="🔁 𑁉 Gewinner neu auslosen")
    @app_commands.describe(giveaway_id="Giveaway ID")
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, err = await self.service.reroll(interaction.guild, int(giveaway_id))
        if not ok:
            return await interaction.response.send_message(f"Reroll fehlgeschlagen: `{err}`", ephemeral=True)
        await interaction.response.send_message("Reroll durchgeführt.", ephemeral=True)


class GiveawayCreateModal(discord.ui.Modal):
    def __init__(self, service: GiveawayService, channel_id: int, winners: int):
        super().__init__(title="🎉 Giveaway erstellen")
        self.service = service
        self.channel_id = int(channel_id)
        self.winners = int(max(1, winners))

        self.title_in = discord.ui.TextInput(label="Titel/Preis", max_length=100, required=True)
        self.sponsor_in = discord.ui.TextInput(label="Sponsor (optional)", max_length=60, required=False)
        self.description_in = discord.ui.TextInput(
            label="Beschreibung (optional)",
            max_length=200,
            required=False,
            style=discord.TextStyle.paragraph,
        )
        self.duration_in = discord.ui.TextInput(
            label="Dauer (z.B. 30m, 2h, 3d)",
            max_length=8,
            required=True,
            placeholder="2h",
        )
        self.winners_in = discord.ui.TextInput(
            label="Gewinner",
            max_length=3,
            required=True,
            placeholder=str(self.winners),
        )
        self.add_item(self.title_in)
        self.add_item(self.sponsor_in)
        self.add_item(self.description_in)
        self.add_item(self.duration_in)
        self.add_item(self.winners_in)

    async def on_submit(self, interaction: discord.Interaction):
        duration = self.service._parse_duration(self.duration_in.value)
        if not duration:
            return await interaction.response.send_message("Ungültige Dauer. Nutze z.B. 30m, 2h, 3d.", ephemeral=True)
        try:
            winners = int(self.winners_in.value)
        except Exception:
            return await interaction.response.send_message("Ungültige Gewinnerzahl.", ephemeral=True)

        data = {
            "title": str(self.title_in.value),
            "sponsor": str(self.sponsor_in.value).strip() or None,
            "description": str(self.description_in.value).strip() or None,
            "duration_minutes": max(1, duration),
            "winner_count": max(1, winners),
            "created_by": interaction.user.id,
        }
        conditions = {
            "min_messages": 0,
            "min_days": 0,
            "min_level": 0,
            "min_voice_hours": 0,
            "min_tickets": 0,
            "min_account_days": 0,
            "required_role_id": 0,
            "excluded_role_id": 0,
            "require_booster": False,
            "require_no_boost": False,
        }
        self.service._pending[interaction.user.id] = (data, conditions, self.channel_id)
        view = GiveawayConditionView(self.service, interaction.user.id)
        await interaction.response.send_message("Bedingungen auswählen:", view=view, ephemeral=True)


class GiveawayConditionSelect(discord.ui.Select):
    def __init__(self, service: GiveawayService, user_id: int):
        self.service = service
        self.user_id = int(user_id)
        options = [
            discord.SelectOption(label="Server Booster", value="require_booster", emoji="🚀"),
            discord.SelectOption(label="Kein Booster", value="require_no_boost", emoji="🚫"),
        ]
        super().__init__(
            placeholder="Optionale Bedingungen wählen…",
            options=options,
            min_values=0,
            max_values=len(options),
        )

    async def callback(self, interaction: discord.Interaction):
        pending = self.service._pending.get(self.user_id)
        if not pending:
            return await interaction.response.send_message("Session abgelaufen. Bitte neu erstellen.", ephemeral=True)
        data, conditions, channel_id = pending
        conditions["require_booster"] = "require_booster" in self.values
        conditions["require_no_boost"] = "require_no_boost" in self.values
        self.service._pending[self.user_id] = (data, conditions, channel_id)
        await interaction.response.send_message("Booster-Bedingungen gespeichert.", ephemeral=True)


class GiveawayConditionView(discord.ui.View):
    def __init__(self, service: GiveawayService, user_id: int):
        super().__init__(timeout=180)
        self.add_item(GiveawayConditionSelect(service, user_id))
        self.add_item(GiveawayAdvancedButton(service, user_id))
        self.add_item(GiveawayCreateButton(service, user_id))


class GiveawayAdvancedButton(discord.ui.Button):
    def __init__(self, service: GiveawayService, user_id: int):
        super().__init__(label="Weitere Bedingungen", style=discord.ButtonStyle.primary)
        self.service = service
        self.user_id = int(user_id)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GiveawayAdvancedModal(self.service, self.user_id))


class GiveawayCreateButton(discord.ui.Button):
    def __init__(self, service: GiveawayService, user_id: int):
        super().__init__(label="Giveaway erstellen", style=discord.ButtonStyle.success)
        self.service = service
        self.user_id = int(user_id)

    async def callback(self, interaction: discord.Interaction):
        pending = self.service._pending.get(self.user_id)
        if not pending:
            return await interaction.response.send_message("Session abgelaufen. Bitte neu erstellen.", ephemeral=True)
        data, conditions, channel_id = pending
        channel = interaction.guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("Zielkanal ungültig.", ephemeral=True)
        await self.service.create_giveaway(interaction.guild, channel, data, conditions)
        self.service._pending.pop(self.user_id, None)
        view = await self.service.build_confirm_embed(interaction.guild, data, conditions)
        await interaction.response.send_message(view=view, ephemeral=True)


class GiveawayAdvancedModal(discord.ui.Modal):
    def __init__(self, service: GiveawayService, user_id: int):
        super().__init__(title="Zusätzliche Bedingungen")
        self.service = service
        self.user_id = int(user_id)
        self.min_messages = discord.ui.TextInput(label="Min. Nachrichten", required=False, placeholder="0")
        self.min_days = discord.ui.TextInput(label="Min. Tage auf Server", required=False, placeholder="0")
        self.min_level = discord.ui.TextInput(label="Min. Level", required=False, placeholder="0")
        self.min_voice = discord.ui.TextInput(label="Min. Voice-Stunden", required=False, placeholder="0")
        self.roles = discord.ui.TextInput(
            label="Rollen/Extras",
            required=False,
            placeholder="required:123 | exclude:456 | tickets:3 | account:30",
        )
        self.add_item(self.min_messages)
        self.add_item(self.min_days)
        self.add_item(self.min_level)
        self.add_item(self.min_voice)
        self.add_item(self.roles)

    async def on_submit(self, interaction: discord.Interaction):
        pending = self.service._pending.get(self.user_id)
        if not pending:
            return await interaction.response.send_message("Session abgelaufen.", ephemeral=True)
        data, conditions, channel_id = pending
        conditions["min_messages"] = _to_int(self.min_messages.value)
        conditions["min_days"] = _to_int(self.min_days.value)
        conditions["min_level"] = _to_int(self.min_level.value)
        conditions["min_voice_hours"] = _to_int(self.min_voice.value)
        required_id, excluded_id, min_tickets, min_account_days = _parse_roles(self.roles.value)
        if required_id:
            conditions["required_role_id"] = required_id
        if excluded_id:
            conditions["excluded_role_id"] = excluded_id
        if min_tickets:
            conditions["min_tickets"] = min_tickets
        if min_account_days:
            conditions["min_account_days"] = min_account_days
        self.service._pending[self.user_id] = (data, conditions, channel_id)
        await interaction.response.send_message("Zusatzbedingungen gespeichert.", ephemeral=True)


def _to_int(v: str | None) -> int:
    try:
        return max(0, int(str(v or "0").strip()))
    except Exception:
        return 0


def _parse_roles(text: str | None) -> tuple[int, int, int, int]:
    required_id = 0
    excluded_id = 0
    min_tickets = 0
    min_account_days = 0
    raw = str(text or "").lower()
    for part in raw.split("|"):
        p = part.strip()
        if p.startswith("required:"):
            required_id = _to_int(p.replace("required:", "").strip())
        if p.startswith("exclude:"):
            excluded_id = _to_int(p.replace("exclude:", "").strip())
        if p.startswith("tickets:"):
            min_tickets = _to_int(p.replace("tickets:", "").strip())
        if p.startswith("account:"):
            min_account_days = _to_int(p.replace("account:", "").strip())
    return required_id, excluded_id, min_tickets, min_account_days

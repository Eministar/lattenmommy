import discord
from discord import app_commands
from discord.ext import commands
from bot.modules.polls.services.poll_service import PollService


class PollCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "poll_service", None) or PollService(bot, bot.settings, bot.db, bot.logger)

    poll = app_commands.Group(name="poll", description="📊 𑁉 Umfrage-Tools")

    @poll.command(name="create", description="🗳️ 𑁉 Umfrage erstellen")
    @app_commands.describe(channel="Zielkanal")
    async def create(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        await interaction.response.send_modal(PollCreateModal(self.service, channel.id))

    @poll.command(name="close", description="⏹️ 𑁉 Umfrage manuell schließen")
    @app_commands.describe(poll_id="Umfrage ID")
    async def close(self, interaction: discord.Interaction, poll_id: int):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        ok, err = await self.service.close_poll(interaction.guild, int(poll_id))
        if not ok:
            messages = {
                "poll_not_found": "Umfrage nicht gefunden.",
                "poll_other_guild": "Diese Umfrage gehört zu einem anderen Server.",
                "poll_already_closed": "Diese Umfrage ist bereits geschlossen.",
            }
            return await interaction.response.send_message(messages.get(err, "Umfrage konnte nicht geschlossen werden."), ephemeral=True)
        await interaction.response.send_message("Umfrage wurde geschlossen.", ephemeral=True)


class PollCreateModal(discord.ui.Modal):
    def __init__(self, service: PollService, channel_id: int):
        super().__init__(title="📊 Umfrage erstellen")
        self.service = service
        self.channel_id = int(channel_id)
        self.question = discord.ui.TextInput(label="Frage", max_length=150, required=True)
        self.options = discord.ui.TextInput(
            label="Optionen (Komma oder neue Zeile)",
            style=discord.TextStyle.paragraph,
            max_length=400,
            required=True,
            placeholder="Option 1, Option 2, Option 3",
        )
        self.emojis = discord.ui.TextInput(
            label="Emojis optional (gleiches Format)",
            max_length=150,
            required=False,
            placeholder="✅, ❌, 🤷",
        )
        self.duration = discord.ui.TextInput(
            label="Dauer optional (z.B. 30m, 2h, 3d)",
            max_length=8,
            required=False,
            placeholder="2h",
        )
        self.image_url = discord.ui.TextInput(
            label="Bild-URL optional",
            max_length=300,
            required=False,
            placeholder="https://example.com/poll.jpg",
        )
        self.add_item(self.question)
        self.add_item(self.options)
        self.add_item(self.emojis)
        self.add_item(self.duration)
        self.add_item(self.image_url)

    async def on_submit(self, interaction: discord.Interaction):
        split_tokens = str(self.options.value).replace("\n", ",")
        raw_opts = [o.strip() for o in split_tokens.split(",") if o.strip()]
        opts = []
        for o in raw_opts:
            if o not in opts:
                opts.append(o)
        if len(opts) < 2:
            return await interaction.response.send_message("Mindestens 2 Optionen angeben.", ephemeral=True)
        if len(opts) > 10:
            return await interaction.response.send_message("Maximal 10 Optionen.", ephemeral=True)

        emoji_tokens = str(self.emojis.value or "").replace("\n", ",")
        raw_emojis = [e.strip() for e in emoji_tokens.split(",") if e.strip()]
        option_data = []
        for i, label in enumerate(opts):
            emoji = raw_emojis[i] if i < len(raw_emojis) else None
            option_data.append({"label": label, "emoji": emoji})

        duration_text = str(self.duration.value or "").strip()
        duration_minutes = None
        if duration_text:
            duration_minutes = self.service._parse_duration(duration_text)
            if not duration_minutes:
                return await interaction.response.send_message("Ungültige Dauer. Nutze z.B. 30m, 2h oder 3d.", ephemeral=True)

        image_url = str(self.image_url.value or "").strip() or None
        if image_url and not (image_url.startswith("http://") or image_url.startswith("https://")):
            return await interaction.response.send_message("Bild-URL muss mit http:// oder https:// starten.", ephemeral=True)

        channel = interaction.guild.get_channel(int(self.channel_id))
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("Zielkanal ungültig.", ephemeral=True)
        await self.service.create_poll(
            interaction.guild,
            channel,
            str(self.question.value),
            option_data,
            interaction.user.id,
            duration_minutes=duration_minutes,
            image_url=image_url,
        )
        await interaction.response.send_message("Umfrage erstellt.", ephemeral=True)

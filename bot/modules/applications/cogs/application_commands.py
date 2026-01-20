import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.applications.services.application_service import ApplicationService
from bot.modules.applications.views.application_panel import ApplicationPanelView
from bot.core.perms import is_staff


class _ApplicationModal(discord.ui.Modal):
    def __init__(self, service: ApplicationService, questions: list[str]):
        super().__init__(title="Bewerbung")
        self.service = service
        self.questions = questions
        self.inputs = []
        for q in questions[:5]:
            inp = discord.ui.TextInput(
                label=str(q)[:45],
                style=discord.TextStyle.paragraph,
                max_length=800,
                required=True,
            )
            self.inputs.append(inp)
            self.add_item(inp)

    async def on_submit(self, interaction: discord.Interaction):
        answers = [(i.value or "").strip() for i in self.inputs]
        ok, err = await self.service.start_application(interaction, answers)
        if ok:
            await interaction.response.send_message("Bewerbung wurde eingereicht. Danke!", ephemeral=True)
        else:
            await interaction.response.send_message(f"Bewerbung konnte nicht gestartet werden: {err}", ephemeral=True)


class ApplicationCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "application_service", None) or ApplicationService(
            bot, bot.settings, bot.db, bot.logger
        )

    @app_commands.command(name="bewerbung", description="📝 𑁉 Bewerbung starten")
    async def application_start(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        has_ticket = await self.service.has_open_ticket(interaction.guild.id, interaction.user.id)
        if has_ticket:
            return await interaction.response.send_message(
                "Du hast bereits ein offenes Ticket. Bitte schließe zuerst dein Ticket, bevor du dich bewirbst.",
                ephemeral=True,
            )
        await self.service.start_dm_flow(interaction.user, interaction.guild)
        await interaction.response.send_message("Ich habe dir eine DM geschickt. Bitte beantworte dort die Fragen.", ephemeral=True)

    application_panel = app_commands.Group(name="applicationpanel", description="📝 𑁉 Bewerbungs-Panel")

    @application_panel.command(name="send", description="📝 𑁉 Bewerbungs-Panel senden")
    @app_commands.describe(channel="Zielkanal (optional)")
    async def application_panel_send(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        target = channel or interaction.channel
        if not isinstance(target, discord.abc.Messageable):
            return await interaction.response.send_message("Zielkanal ungültig.", ephemeral=True)
        content = await self._build_application_panel_content()
        await target.send(content=content, view=ApplicationPanelView())
        await interaction.response.send_message("Panel gesendet.", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is not None:
            return
        await self.service.handle_dm_answer(message)

    async def _fetch_count(self, query: str) -> int:
        conn = (
            getattr(self.bot.db, "conn", None)
            or getattr(self.bot.db, "_conn", None)
            or getattr(self.bot.db, "connection", None)
        )
        if conn is not None:
            cur = await conn.execute(query)
            row = await cur.fetchone()
            try:
                await cur.close()
            except Exception:
                pass
            return int(row[0]) if row and row[0] is not None else 0
        if hasattr(self.bot.db, "execute"):
            cur = await self.bot.db.execute(query)
            row = await cur.fetchone()
            try:
                await cur.close()
            except Exception:
                pass
            return int(row[0]) if row and row[0] is not None else 0
        return 0

    async def _build_application_panel_content(self) -> str:
        total = await self._fetch_count("SELECT COUNT(*) FROM applications")
        open_ = await self._fetch_count("SELECT COUNT(*) FROM applications WHERE status = 'open'")
        return "\n".join(
            [
                "📝 𑁉 BEWERBUNG PANEL",
                "━━━━━━━━━━━━━━━━━━",
                "┏`🧭` - So laeuft die Bewerbung:",
                "┣`1` - Klick auf den Button",
                "┣`2` - Beantworte die Fragen",
                "┗`3` - Team meldet sich im Thread",
                "━━━━━━━━━━━━━━━━━━",
                "┏`📈` - Live Stats",
                f"┣`📝` - Bewerbungen gesamt: {total}",
                f"┗`🟡` - Offen: {open_}",
                "━━━━━━━━━━━━━━━━━━",
            ]
        )

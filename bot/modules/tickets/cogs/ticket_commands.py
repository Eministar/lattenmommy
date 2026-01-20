import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.tickets.services.ticket_service import TicketService
from bot.modules.tickets.views.support_panel import SupportPanelView
from bot.core.perms import is_staff


class TicketCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "ticket_service", None) or TicketService(bot, bot.settings, bot.db, bot.logger)

    ticket = app_commands.Group(name="ticket", description="🎫 𑁉 Ticket-Tools")
    support_panel = app_commands.Group(name="supportpanel", description="🛟 𑁉 Support-Panel")

    @ticket.command(name="beanspruchen", description="🧷 𑁉 Ticket claimen/freigeben")
    async def claim(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        await self.service.toggle_claim(interaction)

    @ticket.command(name="schliessen", description="🔒 𑁉 Ticket schließen")
    async def close(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        await interaction.response.send_message('Nutze bitte den Button "Ticket schließen" im Embed.', ephemeral=True)

    @app_commands.command(name="ticket-add", description="➕ 𑁉 User zum Ticket hinzufügen")
    @app_commands.describe(user="User, der zum Ticket hinzugefügt werden soll")
    async def ticket_add(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        await self.service.add_participant(interaction, user)

    @ticket.command(name="reopen", description="🔓 𑁉 Ticket wieder öffnen")
    async def reopen(self, interaction: discord.Interaction):
        await self.service.reopen_ticket(interaction)

    @ticket.command(name="status", description="🏷️ 𑁉 Ticket-Status ändern")
    @app_commands.describe(label="z.B. wartet_auf_user, on_hold, in_arbeit")
    async def status(self, interaction: discord.Interaction, label: str):
        await self.service.set_status_label(interaction, label)

    @ticket.command(name="priority", description="🚦 𑁉 Ticket-Priorität setzen")
    @app_commands.choices(priority=[
        app_commands.Choice(name="Niedrig (1)", value=1),
        app_commands.Choice(name="Normal (2)", value=2),
        app_commands.Choice(name="Hoch (3)", value=3),
        app_commands.Choice(name="Dringend (4)", value=4),
    ])
    async def priority(self, interaction: discord.Interaction, priority: app_commands.Choice[int]):
        await self.service.set_priority(interaction, int(priority.value))

    @ticket.command(name="escalate", description="⚠️ 𑁉 Ticket eskalieren")
    @app_commands.describe(level="1-5", reason="Optionaler Grund")
    async def escalate(self, interaction: discord.Interaction, level: int, reason: str | None = None):
        await self.service.escalate_ticket(interaction, level, reason)

    @ticket.command(name="category", description="🧭 𑁉 Ticket-Kategorie wechseln")
    @app_commands.describe(key="Kategorie-Key aus config.yml")
    async def category(self, interaction: discord.Interaction, key: str):
        await self.service.change_category(interaction, key)

    @ticket.command(name="transcript", description="🧾 𑁉 Ticket-Transcript erstellen")
    @app_commands.describe(channel="Optionaler Zielkanal (sonst Ticket-Log)")
    async def transcript(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await self.service.send_transcript(interaction, channel)

    @ticket.command(name="weiterleitung", description="🎯 𑁉 Ticket weiterleiten")
    @app_commands.describe(role="Zielrolle", reason="Optionaler Grund")
    async def forward(self, interaction: discord.Interaction, role: discord.Role, reason: str | None = None):
        await self.service.forward_ticket(interaction, role, reason)

    @support_panel.command(name="send", description="🛟 𑁉 Support-Panel senden")
    @app_commands.describe(channel="Zielkanal (optional)")
    async def support_panel_send(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        target = channel or interaction.channel
        if not isinstance(target, discord.abc.Messageable):
            return await interaction.response.send_message("Zielkanal ungültig.", ephemeral=True)
        content = await self._build_support_panel_content()
        await target.send(content=content, view=SupportPanelView())
        await interaction.response.send_message("Panel gesendet.", ephemeral=True)

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

    async def _build_support_panel_content(self) -> str:
        total = await self._fetch_count("SELECT COUNT(*) FROM tickets")
        open_ = await self._fetch_count("SELECT COUNT(*) FROM tickets WHERE status IS NULL OR status != 'closed'")
        active = await self._fetch_count(
            "SELECT COUNT(*) FROM user_stats "
            "WHERE (last_message_at IS NOT NULL AND datetime(last_message_at) >= datetime('now','-1 day')) "
            "OR (last_voice_at IS NOT NULL AND datetime(last_voice_at) >= datetime('now','-1 day'))"
        )
        return "\n".join(
            [
                "🛟 𑁉 SUPPORT PANEL",
                "━━━━━━━━━━━━━━━━━━",
                "┏`📌` - So funktioniert Support:",
                "┣`1` - Klick auf den Button",
                "┣`2` - Ich schicke dir eine DM",
                "┗`3` - Schreib dein Anliegen",
                "━━━━━━━━━━━━━━━━━━",
                "┏`📈` - Live Stats",
                f"┣`🎫` - Tickets gesamt: {total}",
                f"┣`🟢` - Offene Tickets: {open_}",
                f"┗`👥` - Aktive User (24h): {active}",
                "━━━━━━━━━━━━━━━━━━",
            ]
        )

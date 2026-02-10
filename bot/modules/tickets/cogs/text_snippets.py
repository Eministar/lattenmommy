import discord
from discord import app_commands
from discord.ext import commands

from bot.core.perms import is_staff
from bot.modules.tickets.services.ticket_service import TicketService
from bot.modules.tickets.formatting.snippet_embeds import build_snippet_embed, build_snippet_list_embed
from bot.utils.emojis import em


from bot.utils.emojis import em

def _default_snippets(settings, guild) -> dict:
    arrow2 = em(settings, "arrow2", guild) or "»"

    return {
        "entbannung": {
            "title": " 𑁉 ENTBANNUNG",
            "body": (
                f" Damit wir deine Entbannung prüfen können, brauchen wir kurz ein paar Infos.\n\n"
                "┏`🎮` - Ingame-Name\n"
                "┣`⏰` - Uhrzeit/Datum vom Bann\n"
                "┣`🧾` - Grund (wenn angezeigt)\n"
                "┗`📝` - Warum du entbannt werden solltest\n\n"
                f"{arrow2} Sobald wir das haben, schauen wir’s uns an."
            ),
        },
        "beschaeftigt": {
            "title": " 𑁉 WIR SIND GERADE BESCHÄFTIGT",
            "body": (
                f"Danke für deine Nachricht! Gerade ist gut was los.\n\n"
                "┏`🕒` - Wir melden uns so schnell wie möglich\n"
                "┗`💜` - Bitte hab kurz Geduld, wir sind dran."
            ),
        },
        "dokumentation": {
            "title": " 𑁉 DOKUMENTATION ANSEHEN",
            "body": (
                f" Bitte schau zuerst in die Doku – vieles ist dort schon erklärt.\n\n"
                "┏`🔎` - Such dort nach deinem Thema\n"
                "┗`✅` - Wenn’s dann noch klemmt, schreib uns hier weiter."
            ),
        },
    }



def _load_snippets(settings, guild) -> dict:
    if guild:
        data = settings.get_guild(guild.id, "ticket.snippets", {}) or {}
    else:
        data = settings.get("ticket.snippets", {}) or {}
    if isinstance(data, dict) and data:
        return data
    return _default_snippets(settings, guild)


class TextSnippetsCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "ticket_service", None) or TicketService(bot, bot.settings, bot.db, bot.logger)

    snippets = app_commands.Group(name="text-snippets", description="📝 𑁉 Vorgefertigte Nachrichten")

    @snippets.command(name="list", description="📋 𑁉 Snippets anzeigen")
    async def list_snippets(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)

        data = _load_snippets(self.bot.settings, interaction.guild)
        items = []
        for k, v in data.items():
            title = str(v.get("title", k)).strip()
            items.append((str(k), title))

        view = build_snippet_list_embed(self.bot.settings, interaction.guild, items)
        await interaction.response.send_message(view=view, ephemeral=True)

    @snippets.command(name="send", description="✉️ 𑁉 Snippet im Ticket senden")
    @app_commands.describe(key="Key des Snippets")
    async def send_snippet(self, interaction: discord.Interaction, key: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not is_staff(self.bot.settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await interaction.response.send_message("Nur im Ticket-Thread.", ephemeral=True)

        forum_id = self.bot.settings.get_guild_int(interaction.guild.id, "bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await interaction.response.send_message("Nur im Ticket-Thread.", ephemeral=True)

        data = _load_snippets(self.bot.settings, interaction.guild)
        found = None
        for k, v in data.items():
            if str(k).lower() == str(key).lower():
                found = (str(k), v)
                break
        if not found:
            return await interaction.response.send_message("Snippet nicht gefunden.", ephemeral=True)

        ticket = await self.service.get_ticket_from_thread(interaction.guild.id, thread.id)
        if not ticket:
            return await interaction.response.send_message("Ticket nicht gefunden.", ephemeral=True)

        title = str(found[1].get("title", found[0])).strip()
        body = str(found[1].get("body", "")).strip()
        view = build_snippet_embed(self.bot.settings, interaction.guild, found[0], title, body)

        try:
            await thread.send(view=view)
        except Exception:
            pass

        recipients = await self.service.get_participant_ids(int(ticket["ticket_id"]), int(ticket.get("user_id") or 0))
        for uid in recipients:
            try:
                user = await self.bot.fetch_user(int(uid))
                await user.send(view=view)
            except Exception:
                pass

        await interaction.response.send_message(f'Snippet "{found[0]}" gesendet.', ephemeral=True)

    @send_snippet.autocomplete("key")
    async def send_snippet_autocomplete(self, interaction: discord.Interaction, current: str):
        data = _load_snippets(self.bot.settings, interaction.guild)
        keys = [str(k) for k in data.keys()]
        current_lower = (current or "").lower()
        matches = [k for k in keys if current_lower in k.lower()]
        return [app_commands.Choice(name=k, value=k) for k in matches[:25]]

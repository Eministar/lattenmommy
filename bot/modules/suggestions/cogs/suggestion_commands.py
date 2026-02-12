import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.suggestions.services.suggestion_service import SuggestionService


class SuggestionCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.service = getattr(bot, "suggestion_service", None) or SuggestionService(bot, bot.settings, bot.db, bot.logger)

    vorschlag = app_commands.Group(name="vorschlag", description="💡 𑁉 Vorschlags-Tools")
    vorschlagpanel = app_commands.Group(name="vorschlagpanel", description="💡 𑁉 Vorschlagspanel")

    @vorschlagpanel.command(name="send", description="💡 𑁉 Vorschlagspanel senden/aktualisieren")
    @app_commands.describe(forum="Optionales Vorschlags-Forum")
    async def panel_send(self, interaction: discord.Interaction, forum: discord.ForumChannel | None = None):
        await self.service.send_panel(interaction, forum=forum)

    @vorschlag.command(name="status", description="🏷️ 𑁉 Status im Vorschlags-Thread setzen")
    @app_commands.describe(status="Neuer Status")
    @app_commands.choices(status=[
        app_commands.Choice(name="Pending", value="pending"),
        app_commands.Choice(name="Reviewing", value="reviewing"),
        app_commands.Choice(name="Accepted", value="accepted"),
        app_commands.Choice(name="Denied", value="denied"),
        app_commands.Choice(name="Implemented", value="implemented"),
    ])
    async def set_status(self, interaction: discord.Interaction, status: app_commands.Choice[str]):
        await self.service.set_status(interaction, str(status.value))

    @vorschlag.command(name="antwort", description="📝 𑁉 Admin-Response im Vorschlags-Thread setzen")
    @app_commands.describe(text="Antwort vom Team")
    async def set_response(self, interaction: discord.Interaction, text: str):
        await self.service.set_admin_response(interaction, text)


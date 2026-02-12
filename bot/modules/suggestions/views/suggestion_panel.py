from __future__ import annotations

import discord

from bot.modules.suggestions.formatting.suggestion_embeds import build_suggestion_panel_container


class SuggestionSubmitModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="💡 Vorschlag einreichen")
        self.title_input = discord.ui.TextInput(
            label="Titel",
            required=True,
            max_length=120,
            style=discord.TextStyle.short,
            placeholder="Kurzer Titel für deinen Vorschlag",
        )
        self.content_input = discord.ui.TextInput(
            label="Beschreibung",
            required=True,
            max_length=2000,
            style=discord.TextStyle.paragraph,
            placeholder="Erkläre deinen Vorschlag möglichst konkret.",
        )
        self.add_item(self.title_input)
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "suggestion_service", None)
        if not service:
            return await interaction.response.send_message("Suggestion-Service nicht verfügbar.", ephemeral=True)
        await service.submit_suggestion(interaction, str(self.title_input.value), str(self.content_input.value))


class SuggestionPanelButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Vorschlag einreichen",
            style=discord.ButtonStyle.primary,
            custom_id="starry:suggestion_submit",
            emoji="💡",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(SuggestionSubmitModal())


class SuggestionPanelView(discord.ui.LayoutView):
    def __init__(self, settings=None, guild: discord.Guild | None = None):
        super().__init__(timeout=None)
        container = build_suggestion_panel_container(settings, guild, SuggestionPanelButton())
        self.add_item(container)


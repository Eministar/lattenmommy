import discord


class SupportPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Ticket starten",
        style=discord.ButtonStyle.primary,
        custom_id="support_panel_start",
        emoji="🎫",
    )
    async def start_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        try:
            await interaction.user.send(
                "🧩 𑁉 SUPPORT START\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "Schreib mir jetzt kurz dein Anliegen.\n"
                "Ich erstelle dann automatisch dein Ticket."
            )
            await interaction.response.send_message("Ich habe dir eine DM geschickt.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("DM nicht moeglich. Bitte DMs aktivieren.", ephemeral=True)

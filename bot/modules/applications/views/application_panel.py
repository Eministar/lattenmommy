import discord

from bot.modules.applications.services.application_service import ApplicationService


class ApplicationPanelModal(discord.ui.Modal):
    def __init__(self, service: ApplicationService):
        super().__init__(title="Bewerbung")
        self.service = service
        self.questions = service._questions()
        self.inputs = []
        for q in self.questions[:5]:
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


class ApplicationPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Bewerbung starten",
        style=discord.ButtonStyle.primary,
        custom_id="application_panel_start",
        emoji="📝",
    )
    async def start_application(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        bot = interaction.client
        service = getattr(bot, "application_service", None) or ApplicationService(
            bot, bot.settings, bot.db, bot.logger
        )
        has_ticket = await service.has_open_ticket(interaction.guild.id, interaction.user.id)
        if has_ticket:
            return await interaction.response.send_message(
                "Du hast bereits ein offenes Ticket. Bitte schliesse zuerst dein Ticket.",
                ephemeral=True,
            )
        await interaction.response.send_modal(ApplicationPanelModal(service))

import re
import discord

from bot.core.perms import is_staff


class ApplicationDecisionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"starry:app_decide:(?P<app_id>\d+):(?P<decision>accept|deny)",
):
    def __init__(self, app_id: int, decision: str):
        self.app_id = int(app_id)
        self.decision = str(decision)
        label = "Annehmen" if self.decision == "accept" else "Ablehnen"
        style = discord.ButtonStyle.success if self.decision == "accept" else discord.ButtonStyle.danger
        emoji = "✅" if self.decision == "accept" else "⛔"
        btn = discord.ui.Button(
            custom_id=f"starry:app_decide:{self.app_id}:{self.decision}",
            label=label,
            style=style,
            emoji=emoji,
        )
        super().__init__(btn)

    @classmethod
    def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(int(match["app_id"]), str(match["decision"]))

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        settings = getattr(interaction.client, "settings", None)
        if not settings or not is_staff(settings, interaction.user):
            return await interaction.response.send_message("Keine Rechte.", ephemeral=True)

        service = getattr(interaction.client, "application_service", None)
        if not service:
            return await interaction.response.send_message("Application-Service nicht bereit.", ephemeral=True)

        try:
            await interaction.response.defer(ephemeral=True)
        except discord.InteractionResponded:
            pass

        accepted = self.decision == "accept"
        ok, err = await service.decide_application(interaction, self.app_id, accepted)
        if not ok:
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"Aktion fehlgeschlagen: {err}", ephemeral=True)
                else:
                    await interaction.response.send_message(f"Aktion fehlgeschlagen: {err}", ephemeral=True)
            except Exception:
                pass
            return

        try:
            if interaction.response.is_done():
                await interaction.followup.send("Entscheidung gespeichert.", ephemeral=True)
            else:
                await interaction.response.send_message("Entscheidung gespeichert.", ephemeral=True)
        except Exception:
            pass

        if interaction.message:
            view = ApplicationDecisionView(self.app_id)
            view.disable_all()
            try:
                await interaction.message.edit(view=view)
            except Exception:
                pass


class ApplicationDecisionView(discord.ui.View):
    def __init__(self, app_id: int):
        super().__init__(timeout=None)
        self.app_id = int(app_id)
        self.add_item(ApplicationDecisionButton(self.app_id, "accept"))
        self.add_item(ApplicationDecisionButton(self.app_id, "deny"))

    def disable_all(self):
        for item in self.children:
            try:
                item.disabled = True
            except Exception:
                pass

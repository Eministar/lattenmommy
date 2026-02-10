import re
import discord

from bot.core.perms import is_staff


async def _handle_decision(interaction: discord.Interaction, app_id: int, accepted: bool):
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        return False, None
    settings = getattr(interaction.client, "settings", None)
    if not settings or not is_staff(settings, interaction.user):
        await interaction.response.send_message("Keine Rechte.", ephemeral=True)
        return False, None

    service = getattr(interaction.client, "application_service", None)
    if not service:
        await interaction.response.send_message("Application-Service nicht bereit.", ephemeral=True)
        return False, None

    try:
        await interaction.response.defer(ephemeral=True)
    except discord.InteractionResponded:
        pass

    ok, err = await service.decide_application(interaction, int(app_id), bool(accepted))
    if not ok:
        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"Aktion fehlgeschlagen: {err}", ephemeral=True)
            else:
                await interaction.response.send_message(f"Aktion fehlgeschlagen: {err}", ephemeral=True)
        except Exception:
            pass
        return False, service

    try:
        if interaction.response.is_done():
            await interaction.followup.send("Entscheidung gespeichert.", ephemeral=True)
        else:
            await interaction.response.send_message("Entscheidung gespeichert.", ephemeral=True)
    except Exception:
        pass
    return True, service


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
        accepted = self.decision == "accept"
        ok, service = await _handle_decision(interaction, self.app_id, accepted)
        if ok and service and interaction.message:
            try:
                view = await service.build_application_submission_view(interaction.guild, self.app_id, disabled=True)
                if view:
                    await interaction.message.edit(view=view)
            except Exception:
                pass


class ApplicationDecisionView(discord.ui.LayoutView):
    def __init__(self, app_id: int, container: discord.ui.Container | None = None, disabled: bool = False):
        super().__init__(timeout=None)
        self.app_id = int(app_id)
        if container:
            self.add_item(container)

        row = discord.ui.ActionRow()
        self.btn_accept = discord.ui.Button(
            custom_id=f"starry:app_decide:{self.app_id}:accept",
            label="Annehmen",
            style=discord.ButtonStyle.success,
            emoji="✅",
            disabled=disabled,
        )
        self.btn_accept.callback = self._make_cb(True)
        self.btn_deny = discord.ui.Button(
            custom_id=f"starry:app_decide:{self.app_id}:deny",
            label="Ablehnen",
            style=discord.ButtonStyle.danger,
            emoji="⛔",
            disabled=disabled,
        )
        self.btn_deny.callback = self._make_cb(False)
        row.add_item(self.btn_accept)
        row.add_item(self.btn_deny)
        self.add_item(row)

    def _make_cb(self, accepted: bool):
        async def _cb(interaction: discord.Interaction):
            ok, service = await _handle_decision(interaction, self.app_id, accepted)
            if ok and service and interaction.message:
                try:
                    view = await service.build_application_submission_view(interaction.guild, self.app_id, disabled=True)
                    if view:
                        await interaction.message.edit(view=view)
                except Exception:
                    pass
        return _cb

    def disable_all(self):
        for item in self.children:
            try:
                item.disabled = True
            except Exception:
                pass

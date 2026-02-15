from __future__ import annotations

import discord


class FlagDashboardButton(discord.ui.Button):
    def __init__(self, action: str):
        labels = {
            "normal": ("Rätsel", "🎯", discord.ButtonStyle.success),
            "easy": ("Easy", "✨", discord.ButtonStyle.primary),
            "daily": ("Daily", "📆", discord.ButtonStyle.primary),
            "leaderboard": ("Leaderboard", "🏆", discord.ButtonStyle.secondary),
            "streaks": ("Streaks", "🔥", discord.ButtonStyle.secondary),
        }
        label, emoji, style = labels.get(action, ("Aktion", "🧩", discord.ButtonStyle.secondary))
        super().__init__(label=label, emoji=emoji, style=style, custom_id=f"starry:flag_dash:{action}")

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild or not interaction.channel or not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        action = str(self.custom_id).split(":")[-1]
        service = getattr(interaction.client, "flag_quiz_service", None)
        if not service:
            return await interaction.response.send_message("Flag-Service nicht verfügbar.", ephemeral=True)
        if action in {"normal", "easy", "daily"}:
            ok, msg = await service.start_round(interaction.guild, interaction.channel, interaction.user, action)
            return await interaction.response.send_message(msg, ephemeral=True)
        if action == "leaderboard":
            text = await service.leaderboard_text(interaction.guild, limit=10)
            return await interaction.response.send_message(f"**🏆 Leaderboard**\n{text}", ephemeral=True)
        if action == "streaks":
            text = await service.streaks_text(interaction.guild, limit=10)
            return await interaction.response.send_message(f"**🔥 Streaks**\n{text}", ephemeral=True)
        await interaction.response.send_message("Unbekannte Aktion.", ephemeral=True)


class FlagEasyAnswerButton(discord.ui.Button):
    def __init__(self, custom_id: str, label: str):
        super().__init__(label=label[:80], style=discord.ButtonStyle.primary, custom_id=custom_id)

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "flag_quiz_service", None)
        if not service:
            return await interaction.response.send_message("Flag-Service nicht verfügbar.", ephemeral=True)
        code = str(self.custom_id).split(":")[-1]
        await service.handle_easy_button(interaction, code)


class FlagEasyAnswerView(discord.ui.View):
    def __init__(self, button_map: dict[str, tuple[str, str]], timeout: float | None = 35):
        super().__init__(timeout=timeout)
        for cid, payload in button_map.items():
            _code, label = payload
            self.add_item(FlagEasyAnswerButton(cid, label))

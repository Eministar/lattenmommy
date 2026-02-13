from __future__ import annotations

import discord

from bot.modules.roles.formatting.roles_info_embeds import (
    build_roles_info_panel_container,
    build_roles_category_view,
)


class RolesInfoCategorySelect(discord.ui.Select):
    def __init__(self, settings, guild: discord.Guild | None = None):
        self.settings = settings
        self.guild_ref = guild
        options = [
            discord.SelectOption(label="Erfolge", value="achievements", emoji="🏆", description="Erfolgsrollen anzeigen"),
            discord.SelectOption(label="Level", value="level", emoji="⭐", description="Levelrollen anzeigen"),
            discord.SelectOption(label="Sonder", value="special", emoji="✨", description="Sonderrollen anzeigen"),
            discord.SelectOption(label="Teamrollen", value="team", emoji="🛡️", description="Teamrollen anzeigen"),
        ]
        super().__init__(
            custom_id="starry:roles_info_category",
            placeholder="Rollen-Kategorie auswählen",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        category = str(self.values[0])
        view = build_roles_category_view(self.settings, interaction.guild, category)
        target = interaction.channel
        if not isinstance(target, discord.abc.Messageable):
            return await interaction.response.send_message("Kanal ungültig.", ephemeral=True)
        await target.send(view=view)
        await interaction.response.send_message("Rollen-Info gesendet.", ephemeral=True)


class RolesInfoPanelView(discord.ui.LayoutView):
    def __init__(self, settings=None, guild: discord.Guild | None = None):
        super().__init__(timeout=None)
        select = RolesInfoCategorySelect(settings, guild)
        container = build_roles_info_panel_container(settings, guild, select)
        self.add_item(container)


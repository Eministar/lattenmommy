from __future__ import annotations

import discord


class PartyCreateModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Partei gründen")
        self.service = service
        self.name_input = discord.ui.TextInput(
            label="Parteiname",
            placeholder="z. B. Fortschrittspartei",
            style=discord.TextStyle.short,
            min_length=3,
            max_length=50,
            required=True,
        )
        self.desc_input = discord.ui.TextInput(
            label="Kurzbeschreibung",
            placeholder="Kurz euer Fokus/Programm",
            style=discord.TextStyle.paragraph,
            min_length=10,
            max_length=500,
            required=True,
        )
        self.members_input = discord.ui.TextInput(
            label="Mitglieder (User IDs, optional)",
            placeholder="123..., 456... (mind. 3 Mitglieder gesamt inkl. dir)",
            style=discord.TextStyle.paragraph,
            max_length=350,
            required=False,
        )
        self.add_item(self.name_input)
        self.add_item(self.desc_input)
        self.add_item(self.members_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.create_party_from_modal(
            interaction,
            name=str(self.name_input.value or ""),
            description=str(self.desc_input.value or ""),
            member_ids_raw=str(self.members_input.value or ""),
        )


class PartyCreateButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Partei gründen",
            style=discord.ButtonStyle.primary,
            emoji="🏛️",
            custom_id="starry:party:create",
        )

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyCreateModal(service))


class PartyCreatePanelView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_colour=0xB16B91)
        container.add_item(
            discord.ui.TextDisplay(
                "**🏛️ 𑁉 PARTEI-GRÜNDUNG**\n"
                "Du hast die Kandidatenrolle? Dann kannst du hier deine Partei beantragen.\n\n"
                "**Ablauf**\n"
                "┏`📝` - Antrag absenden\n"
                "┣`👥` - Mindestens 3 Mitglieder notwendig\n"
                "┣`🛡️` - Team prüft den Antrag\n"
                "┗`📂` - Nach Genehmigung wird eure Kategorie erstellt"
            )
        )
        container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(PartyCreateButton())
        container.add_item(row)
        self.add_item(container)


class PartyLogoModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Parteilogo setzen")
        self.service = service
        self.url_input = discord.ui.TextInput(
            label="Logo URL",
            placeholder="https://...",
            style=discord.TextStyle.short,
            max_length=400,
            required=True,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.update_party_logo(interaction, str(self.url_input.value or ""))


class PartyProgramModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Parteiprogramm einreichen")
        self.service = service
        self.program_input = discord.ui.TextInput(
            label="Parteiprogramm",
            placeholder="Beschreibt euer Programm...",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=True,
        )
        self.add_item(self.program_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.submit_party_program(interaction, str(self.program_input.value or ""))


class PartyBasicsModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Partei-Basisdaten")
        self.service = service
        self.name_input = discord.ui.TextInput(
            label="Neuer Parteiname",
            style=discord.TextStyle.short,
            min_length=3,
            max_length=50,
            required=True,
        )
        self.desc_input = discord.ui.TextInput(
            label="Neue Beschreibung",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=True,
        )
        self.add_item(self.name_input)
        self.add_item(self.desc_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.update_party_basic_info(
            interaction,
            str(self.name_input.value or ""),
            str(self.desc_input.value or ""),
        )


class PartyTransferLeaderModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Parteichef übertragen")
        self.service = service
        self.user_id_input = discord.ui.TextInput(
            label="Neue Chef User-ID",
            style=discord.TextStyle.short,
            max_length=30,
            required=True,
        )
        self.add_item(self.user_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.transfer_party_leadership(interaction, str(self.user_id_input.value or ""))


class PartyMemberAddModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Mitglied hinzufügen")
        self.service = service
        self.user_id_input = discord.ui.TextInput(
            label="User ID",
            placeholder="Discord User ID",
            style=discord.TextStyle.short,
            max_length=30,
            required=True,
        )
        self.add_item(self.user_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.add_party_member_from_panel(interaction, str(self.user_id_input.value or ""))


class PartyMemberRemoveModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="Mitglied entfernen")
        self.service = service
        self.user_id_input = discord.ui.TextInput(
            label="User ID",
            placeholder="Discord User ID",
            style=discord.TextStyle.short,
            max_length=30,
            required=True,
        )
        self.add_item(self.user_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.remove_party_member_from_panel(interaction, str(self.user_id_input.value or ""))


class PartyLogoButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Logo setzen", style=discord.ButtonStyle.secondary, emoji="🖼️", custom_id="starry:party:logo")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyLogoModal(service))


class PartyProgramButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Programm einreichen", style=discord.ButtonStyle.primary, emoji="📜", custom_id="starry:party:program")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyProgramModal(service))


class PartyBasicsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Name/Bio", style=discord.ButtonStyle.secondary, emoji="📝", custom_id="starry:party:basics")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyBasicsModal(service))


class PartyTransferLeaderButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Chef übertragen", style=discord.ButtonStyle.secondary, emoji="👑", custom_id="starry:party:leader:transfer")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyTransferLeaderModal(service))


class PartyMemberAddButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Mitglied hinzufügen", style=discord.ButtonStyle.success, emoji="➕", custom_id="starry:party:member:add")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyMemberAddModal(service))


class PartyMemberRemoveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Mitglied entfernen", style=discord.ButtonStyle.danger, emoji="➖", custom_id="starry:party:member:remove")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await interaction.response.send_modal(PartyMemberRemoveModal(service))


class PartyLogoClearButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Logo entfernen", style=discord.ButtonStyle.secondary, emoji="🧽", custom_id="starry:party:logo:clear")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await service.clear_party_logo(interaction)


class PartySyncInfoButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Info sync", style=discord.ButtonStyle.secondary, emoji="🔄", custom_id="starry:party:sync")

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "parlament_service", None)
        if not service:
            return await interaction.response.send_message("Partei-Service nicht verfügbar.", ephemeral=True)
        await service.sync_party_public_info(interaction)


class PartySettingsPanelView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_colour=0xB16B91)
        container.add_item(
            discord.ui.TextDisplay(
                "**⚙️ 𑁉 PARTEI-EINSTELLUNGEN**\n"
                "Dieses Panel gehört in euren Partei-Panel-Channel.\n\n"
                "┏`🖼️` - Logo hinterlegen\n"
                "┣`📜` - Programm direkt posten (Text/PDF im Panel-Channel)\n"
                "┣`📝` - Name/Beschreibung anpassen\n"
                "┣`👑` - Parteichef übertragen\n"
                "┣`➕` - Mitglieder hinzufügen\n"
                "┣`➖` - Mitglieder entfernen\n"
                "┗`🔄` - Öffentliche Thread-Info synchronisieren\n\n"
                "Nur der Parteichef darf hier schreiben."
            )
        )
        container.add_item(discord.ui.Separator())
        row1 = discord.ui.ActionRow()
        row1.add_item(PartyLogoButton())
        row1.add_item(PartyProgramButton())
        row1.add_item(PartyBasicsButton())
        container.add_item(row1)
        row2 = discord.ui.ActionRow()
        row2.add_item(PartyTransferLeaderButton())
        row2.add_item(PartyMemberAddButton())
        row2.add_item(PartyMemberRemoveButton())
        container.add_item(row2)
        row3 = discord.ui.ActionRow()
        row3.add_item(PartyLogoClearButton())
        row3.add_item(PartySyncInfoButton())
        container.add_item(row3)
        self.add_item(container)

import discord
from bot.core.perms import is_staff


class RenameModal(discord.ui.Modal):
    def __init__(self, service, channel_id: int):
        super().__init__(title="✏️ Temp-Voice umbenennen")
        self.service = service
        self.channel_id = int(channel_id)
        self.name = discord.ui.TextInput(
            label="Neuer Name",
            required=True,
            max_length=80,
            style=discord.TextStyle.short,
            placeholder="z.B. Chill Lounge",
        )
        self.add_item(self.name)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.rename_channel(interaction, self.channel_id, self.name.value)


class LimitModal(discord.ui.Modal):
    def __init__(self, service, channel_id: int):
        super().__init__(title="👥 User-Limit setzen")
        self.service = service
        self.channel_id = int(channel_id)
        self.limit = discord.ui.TextInput(
            label="Limit (0 = unbegrenzt)",
            required=True,
            max_length=3,
            style=discord.TextStyle.short,
            placeholder="0",
        )
        self.add_item(self.limit)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.set_user_limit(interaction, self.channel_id, self.limit.value)


class BitrateModal(discord.ui.Modal):
    def __init__(self, service, channel_id: int):
        super().__init__(title="🎛️ Bitrate setzen")
        self.service = service
        self.channel_id = int(channel_id)
        self.bitrate = discord.ui.TextInput(
            label="Bitrate in kbps (z.B. 64)",
            required=True,
            max_length=4,
            style=discord.TextStyle.short,
            placeholder="64",
        )
        self.add_item(self.bitrate)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.set_bitrate(interaction, self.channel_id, self.bitrate.value)


class ActionSelect(discord.ui.Select):
    def __init__(self, view):
        options = [
            discord.SelectOption(label="Invite", value="invite", emoji="📨"),
            discord.SelectOption(label="Block", value="block", emoji="⛔"),
            discord.SelectOption(label="Unblock", value="unblock", emoji="✅"),
            discord.SelectOption(label="Kick", value="kick", emoji="👢"),
            discord.SelectOption(label="Mute", value="mute", emoji="🔇"),
            discord.SelectOption(label="Unmute", value="unmute", emoji="🔊"),
            discord.SelectOption(label="Deafen", value="deafen", emoji="🙉"),
            discord.SelectOption(label="Undeafen", value="undeafen", emoji="🙈"),
            discord.SelectOption(label="Transfer", value="transfer", emoji="👑"),
        ]
        super().__init__(
            placeholder="Aktion waehlen…",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="starry:tempvoice_action",
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.selected_action = self.values[0] if self.values else None
        await self.view_ref.try_execute_action(interaction)


class UserSelect(discord.ui.UserSelect):
    def __init__(self, view):
        super().__init__(
            placeholder="User waehlen…",
            min_values=1,
            max_values=1,
            custom_id="starry:tempvoice_user",
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.selected_user = self.values[0] if self.values else None
        await self.view_ref.try_execute_action(interaction)


class RegionSelect(discord.ui.Select):
    def __init__(self, view):
        options = [
            discord.SelectOption(label="Automatisch", value="auto", emoji="🌍"),
            discord.SelectOption(label="Europa", value="europe", emoji="🇪🇺"),
            discord.SelectOption(label="USA Ost", value="us-east", emoji="🇺🇸"),
            discord.SelectOption(label="USA West", value="us-west", emoji="🇺🇸"),
            discord.SelectOption(label="USA Zentral", value="us-central", emoji="🇺🇸"),
            discord.SelectOption(label="Singapur", value="singapore", emoji="🇸🇬"),
            discord.SelectOption(label="Japan", value="japan", emoji="🇯🇵"),
            discord.SelectOption(label="Hongkong", value="hongkong", emoji="🇭🇰"),
            discord.SelectOption(label="Sydney", value="sydney", emoji="🇦🇺"),
            discord.SelectOption(label="Brazil", value="brazil", emoji="🇧🇷"),
            discord.SelectOption(label="India", value="india", emoji="🇮🇳"),
            discord.SelectOption(label="South Africa", value="southafrica", emoji="🇿🇦"),
            discord.SelectOption(label="Rotterdam", value="rotterdam", emoji="🇳🇱"),
            discord.SelectOption(label="Russia", value="russia", emoji="🇷🇺"),
        ]
        super().__init__(
            placeholder="Region setzen…",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="starry:tempvoice_region",
        )
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        await self.view_ref.service.set_region(interaction, self.view_ref.channel_id, self.values[0])


class TempVoicePanelView(discord.ui.LayoutView):
    def __init__(
        self,
        service,
        channel_id: int,
        owner_id: int,
        locked: bool,
        private: bool,
        container: discord.ui.Container | None = None,
    ):
        super().__init__(timeout=3600)
        self.service = service
        self.channel_id = int(channel_id)
        self.owner_id = int(owner_id)
        self.locked = bool(locked)
        self.private = bool(private)
        self.selected_action = None
        self.selected_user = None

        if container:
            self.add_item(container)

        self.btn_rename = discord.ui.Button(
            label="Name aendern",
            emoji="✏️",
            style=discord.ButtonStyle.primary,
        )
        self.btn_rename.callback = self._on_rename

        self.btn_limit = discord.ui.Button(
            label="User-Limit",
            emoji="👥",
            style=discord.ButtonStyle.secondary,
        )
        self.btn_limit.callback = self._on_limit

        self.btn_bitrate = discord.ui.Button(
            label="Bitrate",
            emoji="🎛️",
            style=discord.ButtonStyle.secondary,
        )
        self.btn_bitrate.callback = self._on_bitrate

        self.btn_lock = discord.ui.Button(
            label="Entsperren" if self.locked else "Sperren",
            emoji="🔓" if self.locked else "🔒",
            style=discord.ButtonStyle.success if self.locked else discord.ButtonStyle.danger,
        )
        self.btn_lock.callback = self._on_lock

        self.btn_public = discord.ui.Button(
            label="Oeffentlich" if self.private else "Privat",
            emoji="🌐" if self.private else "🙈",
            style=discord.ButtonStyle.success if self.private else discord.ButtonStyle.secondary,
        )
        self.btn_public.callback = self._on_public

        self.select_region = RegionSelect(self)

        self.action_select = ActionSelect(self)
        self.user_select = UserSelect(self)

        row_main = discord.ui.ActionRow()
        row_main.add_item(self.btn_rename)
        row_main.add_item(self.btn_limit)
        row_main.add_item(self.btn_bitrate)

        row_lock = discord.ui.ActionRow()
        row_lock.add_item(self.btn_lock)
        row_lock.add_item(self.btn_public)

        row_region = discord.ui.ActionRow()
        row_region.add_item(self.select_region)

        row_action = discord.ui.ActionRow()
        row_action.add_item(self.action_select)

        row_user = discord.ui.ActionRow()
        row_user.add_item(self.user_select)

        self.add_item(row_main)
        self.add_item(row_lock)
        self.add_item(row_region)
        self.add_item(row_action)
        self.add_item(row_user)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
            return False
        if interaction.user.id != self.owner_id and not is_staff(self.service.settings, interaction.user):
            await interaction.response.send_message("Nur der Owner darf das Panel nutzen.", ephemeral=True)
            return False
        return True

    async def _on_rename(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RenameModal(self.service, self.channel_id))

    async def _on_limit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LimitModal(self.service, self.channel_id))

    async def _on_bitrate(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BitrateModal(self.service, self.channel_id))

    async def _on_lock(self, interaction: discord.Interaction):
        await self.service.toggle_lock(interaction, self.channel_id)

    async def _on_public(self, interaction: discord.Interaction):
        await self.service.toggle_privacy(interaction, self.channel_id)

    async def try_execute_action(self, interaction: discord.Interaction):
        if not self.selected_action or not self.selected_user:
            await interaction.response.send_message("Bitte Aktion und User auswaehlen.", ephemeral=True)
            return
        action = str(self.selected_action)
        target = self.selected_user
        await self.service.apply_user_action(interaction, self.channel_id, action, target)

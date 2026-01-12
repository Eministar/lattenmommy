import discord

class TeamNoteModal(discord.ui.Modal, title="Team-Notiz verfassen"):
    text = discord.ui.TextInput(label="Notiz", style=discord.TextStyle.paragraph, max_length=1500, required=True)

    def __init__(self, on_submit_cb):
        super().__init__()
        self.on_submit_cb = on_submit_cb

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_cb(interaction, str(self.text.value))

class CloseTicketModal(discord.ui.Modal, title="Ticket schließen"):
    reason = discord.ui.TextInput(label="Grund (optional)", style=discord.TextStyle.paragraph, max_length=800, required=False)

    def __init__(self, on_submit_cb):
        super().__init__()
        self.on_submit_cb = on_submit_cb

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_cb(interaction, str(self.reason.value or "").strip())

class RatingCommentModal(discord.ui.Modal, title="Optionaler Kommentar"):
    comment = discord.ui.TextInput(label="Kommentar", style=discord.TextStyle.paragraph, max_length=800, required=False)

    def __init__(self, on_submit_cb):
        super().__init__()
        self.on_submit_cb = on_submit_cb

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_submit_cb(interaction, str(self.comment.value or "").strip())

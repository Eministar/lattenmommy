import re
import discord


class RatingButton(discord.ui.DynamicItem[discord.ui.Button], template=r"starry:rating:(?P<ticket_id>\d+):(?P<rating>\d+)"):
    def __init__(self, ticket_id: int, rating: int):
        self.ticket_id = int(ticket_id)
        self.rating = int(rating)
        btn = discord.ui.Button(
            custom_id=f"starry:rating:{self.ticket_id}:{self.rating}",
            style=discord.ButtonStyle.primary,
            label=("⭐" * self.rating),
        )
        super().__init__(btn)

    @classmethod
    def from_custom_id(cls, interaction: discord.Interaction, item: discord.ui.Button, match: re.Match[str]):
        return cls(int(match["ticket_id"]), int(match["rating"]))

    async def callback(self, interaction: discord.Interaction):
        service = getattr(interaction.client, "ticket_service", None)
        if not service:
            await interaction.response.send_message("Ticket-Service nicht bereit.", ephemeral=True)
            return
        await interaction.response.send_modal(RatingCommentModal(service, self.ticket_id, self.rating))


class RatingCommentModal(discord.ui.Modal):
    def __init__(self, service, ticket_id: int, rating: int):
        super().__init__(title=f"Bewertung: {rating} ⭐")
        self.service = service
        self.ticket_id = int(ticket_id)
        self.rating = int(rating)

        self.comment = discord.ui.TextInput(
            label="Kommentar (optional)",
            required=False,
            max_length=500,
            style=discord.TextStyle.paragraph,
            placeholder="Wenn du magst: kurz sagen was gut/schlecht war.",
        )
        self.add_item(self.comment)

    async def on_submit(self, interaction: discord.Interaction):
        text = (self.comment.value or "").strip()
        await self.service.submit_rating(interaction, self.ticket_id, self.rating, text if text else None)


class RatingView(discord.ui.LayoutView):
    def __init__(self, service, ticket_id: int, container: discord.ui.Container | None = None):
        super().__init__(timeout=600)
        self.service = service
        self.ticket_id = int(ticket_id)

        if container:
            self.add_item(container)

        row = discord.ui.ActionRow()
        for r in range(1, 6):
            btn = discord.ui.Button(
                custom_id=f"starry:rating:{ticket_id}:{r}",
                style=discord.ButtonStyle.primary,
                label=("⭐" * r),
            )
            btn.callback = self._make_cb(r)
            row.add_item(btn)
        self.add_item(row)

    def _make_cb(self, rating: int):
        async def _cb(interaction: discord.Interaction):
            await interaction.response.send_modal(RatingCommentModal(self.service, self.ticket_id, rating))
        return _cb

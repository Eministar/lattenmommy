import discord


class ParliamentVoteSelect(discord.ui.Select):
    def __init__(self, service, vote_id: int, candidate_options: list[tuple[int, str]], custom_id: str | None = None):
        self.service = service
        self.vote_id = int(vote_id)
        opts = []
        for cid, label in candidate_options:
            try:
                value = str(int(cid))
            except Exception:
                continue
            clean_label = str(label)[:100] if label else value
            opts.append(discord.SelectOption(label=clean_label, value=value))
        super().__init__(
            placeholder="Kandidaten wählen…",
            options=opts[:25],
            min_values=1,
            max_values=1,
            custom_id=custom_id or f"starry:parlament:vote:{self.vote_id}",
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            candidate_id = int(self.values[0])
        except Exception:
            return await interaction.response.send_message("Ungültige Auswahl.", ephemeral=True)
        await self.service.vote(interaction, self.vote_id, candidate_id)


class ParliamentVoteView(discord.ui.LayoutView):
    def __init__(self, service, vote_id: int, candidate_options: list[tuple[int, str]], custom_id: str | None = None):
        super().__init__(timeout=None)
        row = discord.ui.ActionRow()
        row.add_item(ParliamentVoteSelect(service, vote_id, candidate_options, custom_id=custom_id))
        self.add_item(row)

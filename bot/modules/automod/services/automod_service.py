from __future__ import annotations

import re

import discord

from bot.modules.automod.formatting.automod_embeds import build_blacklist_delete_embed


class AutoModService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(int(guild_id), "automod.enabled", True))

    def _blacklist(self, guild_id: int) -> list[str]:
        raw = self.settings.get_guild(int(guild_id), "automod.blacklist", []) or []
        out: list[str] = []
        for item in raw:
            txt = str(item or "").strip().lower()
            if txt:
                out.append(txt)
        return out

    def _match_word(self, text: str, blacklist: list[str]) -> str | None:
        probe = str(text or "")
        for term in blacklist:
            # Word-boundary match, damit nicht mitten in normalen Wörtern ausgelöst wird.
            pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
            if re.search(pattern, probe, flags=re.IGNORECASE):
                return term
        return None

    async def handle_message(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return
        if not message.content:
            return
        if not self._enabled(message.guild.id):
            return

        blacklist = self._blacklist(message.guild.id)
        if not blacklist:
            return

        hit = self._match_word(message.content, blacklist)
        if not hit:
            return

        try:
            await message.delete()
        except Exception:
            return

        try:
            moderator_id = int(getattr(self.bot.user, "id", 0) or 0)
            await self.db.add_infraction(
                message.guild.id,
                message.author.id,
                moderator_id,
                "automod_blacklist",
                None,
                f"Blacklist-Wort: {hit}",
            )
            total_hits = await self.db.count_recent_infractions(
                message.guild.id,
                message.author.id,
                ["automod_blacklist"],
                0,
            )
        except Exception:
            total_hits = 1

        try:
            emb = build_blacklist_delete_embed(self.settings, message.guild, message.author, int(total_hits))
            await message.channel.send(embed=emb, delete_after=12)
        except Exception:
            pass


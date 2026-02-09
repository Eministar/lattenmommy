import io
import re
import discord
from discord.ext import commands

_CUSTOM_EMOJI_RE = re.compile(r"<(a?):([A-Za-z0-9_]+):(\d{15,20})>")


def _build_custom_emoji_embeds(content: str, limit: int = 10) -> list[discord.Embed]:
    if not content:
        return []
    embeds: list[discord.Embed] = []
    seen: set[tuple[str, bool]] = set()
    for match in _CUSTOM_EMOJI_RE.finditer(content):
        animated = bool(match.group(1))
        emoji_id = match.group(3)
        key = (emoji_id, animated)
        if key in seen:
            continue
        seen.add(key)
        ext = "gif" if animated else "png"
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}?size=128&quality=lossless"
        emb = discord.Embed()
        emb.set_image(url=url)
        embeds.append(emb)
        if len(embeds) >= limit:
            break
    return embeds


class BeichteListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_forum_id(self, guild_id: int) -> int:
        try:
            if not self.bot.settings.get_guild_bool(guild_id, "beichte.enabled", True):
                return 0
            return int(self.bot.settings.get_guild_int(guild_id, "beichte.forum_channel_id", 0))
        except Exception:
            return 0

    async def _is_anonymous_thread(self, guild_id: int, thread_id: int) -> bool:
        row = await self._get_thread_row(guild_id, thread_id)
        if not row:
            return False
        try:
            return bool(int(row[3]))
        except Exception:
            return False

    async def _get_thread_row(self, guild_id: int, thread_id: int):
        try:
            return await self.bot.db.get_beichte_thread(int(guild_id), int(thread_id))
        except Exception:
            return None

    @commands.Cog.listener("on_message")
    async def on_message(self, message: discord.Message):
        if not message or not message.guild:
            return
        if message.author and message.author.bot:
            return
        if message.webhook_id:
            return
        if not isinstance(message.channel, discord.Thread):
            return

        thread = message.channel
        parent = getattr(thread, "parent", None)
        if not parent:
            return
        forum_id = await self._get_forum_id(message.guild.id)
        if not forum_id or int(getattr(parent, "id", 0)) != forum_id:
            return

        row = await self._get_thread_row(message.guild.id, thread.id)
        anonymous = False
        creator_id = None
        if row:
            try:
                anonymous = bool(int(row[3]))
            except Exception:
                anonymous = False
            try:
                creator_id = int(row[2])
            except Exception:
                creator_id = None
        if not anonymous:
            return

        reference = None
        if message.reference and message.reference.message_id:
            try:
                reference = message.to_reference(fail_if_not_exists=False)
            except Exception:
                reference = None

        content = (message.content or "").strip()
        embeds = _build_custom_emoji_embeds(content)
        files = []
        for att in message.attachments:
            try:
                data = await att.read()
                files.append(discord.File(io.BytesIO(data), filename=att.filename))
            except Exception:
                continue

        if not content and not files:
            content = "_[Inhalt entfernt]_"

        try:
            await message.delete()
        except Exception:
            return

        anon_number = None
        try:
            anon_number = await self.bot.db.get_or_create_anonymous_number(
                int(message.guild.id),
                int(thread.id),
                int(message.author.id) if message.author else 0,
            )
        except Exception:
            anon_number = None

        is_creator = creator_id is not None and message.author and int(message.author.id) == int(creator_id)
        label = f"Anonym #{anon_number}" if anon_number else "Anonym"
        if is_creator:
            label = f"{label} (Ersteller)"
        prefix = f"**{label}:** "
        allowed_mentions = discord.AllowedMentions(replied_user=False)
        try:
            await thread.send(
                prefix + content if content else prefix,
                files=files or None,
                embeds=embeds or None,
                reference=reference,
                allowed_mentions=allowed_mentions,
            )
        except Exception:
            try:
                await thread.send(
                    prefix + content if content else prefix,
                    embeds=embeds or None,
                    reference=reference,
                    allowed_mentions=allowed_mentions,
                )
            except Exception:
                try:
                    await thread.send(
                        prefix + content if content else prefix,
                        reference=reference,
                        allowed_mentions=allowed_mentions,
                    )
                except Exception:
                    pass

import io
import discord
from discord.ext import commands


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

        content = (message.content or "").strip()
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

        is_creator = creator_id is not None and message.author and int(message.author.id) == int(creator_id)
        prefix = "**Anonym (Ersteller):** " if is_creator else "**Anonym:** "
        try:
            await thread.send(prefix + content if content else prefix, files=files)
        except Exception:
            try:
                await thread.send(prefix + content if content else prefix)
            except Exception:
                pass

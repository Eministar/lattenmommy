from __future__ import annotations

from datetime import datetime, timezone
import discord

from bot.core.perms import is_staff
from bot.modules.seelsorge.formatting.seelsorge_views import (
    build_submission_view,
    build_thread_info_container,
)
from bot.modules.seelsorge.views.info import SeelsorgeInfoView
from bot.modules.seelsorge.views.panel import SeelsorgePanelView


class SeelsorgeSubmitModal(discord.ui.Modal):
    def __init__(self, service):
        super().__init__(title="🧠 Seelsorge – Einreichen")
        self.service = service
        self.privacy = discord.ui.TextInput(
            label="Privat? (ja/nein)",
            max_length=10,
            required=True,
            placeholder="ja oder nein",
        )
        self.thoughts = discord.ui.TextInput(
            label="Deine Gedanken",
            style=discord.TextStyle.paragraph,
            max_length=1500,
            required=True,
            placeholder="Schreib hier, was dich beschäftigt...",
        )
        self.add_item(self.privacy)
        self.add_item(self.thoughts)

    async def on_submit(self, interaction: discord.Interaction):
        await self.service.submit_entry(interaction, str(self.privacy.value), str(self.thoughts.value))


class SeelsorgeService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _gi(self, guild_id: int, key: str, default: int = 0) -> int:
        return int(self.settings.get_guild_int(guild_id, key, default))

    def _g(self, guild_id: int, key: str, default=None):
        return self.settings.get_guild(guild_id, key, default)

    def _forum_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "seelsorge.forum_channel_id", 0)

    def _panel_thread_name(self, guild_id: int) -> str:
        return str(self._g(guild_id, "seelsorge.panel_thread_name", "🧠 Seelsorge – Info") or "🧠 Seelsorge – Info")

    def _parse_privacy(self, raw: str) -> bool | None:
        t = str(raw or "").strip().lower()
        if t in {"ja", "j", "yes", "y", "true", "1", "anonym", "privat"}:
            return True
        if t in {"nein", "n", "no", "false", "0"}:
            return False
        return None

    async def open_submit_modal(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self.settings.get_guild_bool(interaction.guild.id, "seelsorge.enabled", True):
            return await interaction.response.send_message("Seelsorge ist deaktiviert.", ephemeral=True)
        await interaction.response.send_modal(SeelsorgeSubmitModal(self))

    async def configure(self, guild: discord.Guild, forum_channel: discord.ForumChannel):
        await self.settings.set_guild_override(self.db, guild.id, "seelsorge.forum_channel_id", int(forum_channel.id))

    async def send_panel(self, interaction: discord.Interaction, forum: discord.ForumChannel | None = None):
        if not interaction.guild:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        guild = interaction.guild

        forum_channel = forum or await self._get_forum_channel(guild)
        if not forum_channel:
            return await interaction.response.send_message("Forum-Channel ist nicht konfiguriert.", ephemeral=True)

        if forum:
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.forum_channel_id", int(forum.id))
        await self._ensure_main_thread(guild, forum_channel)
        await interaction.response.send_message("Info + Panel aktualisiert.", ephemeral=True)

    async def submit_entry(self, interaction: discord.Interaction, privacy_raw: str, content: str):
        if not interaction.guild or not interaction.user:
            return await interaction.response.send_message("Nur im Server nutzbar.", ephemeral=True)
        if not self.settings.get_guild_bool(interaction.guild.id, "seelsorge.enabled", True):
            return await interaction.response.send_message("Seelsorge ist deaktiviert.", ephemeral=True)
        guild = interaction.guild
        forum_channel = await self._get_forum_channel(guild)
        if not forum_channel:
            return await interaction.response.send_message("Forum-Channel ist nicht konfiguriert.", ephemeral=True)

        anonymous = self._parse_privacy(privacy_raw)
        if anonymous is None:
            return await interaction.response.send_message("Bitte bei Privat: **ja** oder **nein** angeben.", ephemeral=True)

        text = str(content or "").strip()
        if len(text) < 10:
            return await interaction.response.send_message("Bitte etwas ausführlicher schreiben (min. 10 Zeichen).", ephemeral=True)

        display = interaction.user.display_name
        thread_name = "🧠 Seelsorge · Anonym" if anonymous else f"🧠 Seelsorge · {display}"
        thread_name = thread_name[:100]

        data = {
            "user_id": int(interaction.user.id),
            "content": text,
            "anonymous": bool(anonymous),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        view = build_submission_view(self.settings, guild, data)

        res = await forum_channel.create_thread(
            name=thread_name,
            view=view,
        )

        await self.db.create_seelsorge_thread(
            guild.id,
            int(res.thread.id),
            int(interaction.user.id),
            bool(anonymous),
        )

        try:
            info_view = discord.ui.LayoutView(timeout=None)
            info_container = build_thread_info_container(self.settings, guild)
            info_view.add_item(info_container)
            info_msg = await res.thread.send(view=info_view)
            await info_msg.pin()
        except Exception:
            pass

        await interaction.response.send_message("Danke! Dein Thread wurde erstellt.", ephemeral=True)

    async def _get_forum_channel(self, guild: discord.Guild) -> discord.ForumChannel | None:
        channel_id = self._forum_channel_id(guild.id)
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await guild.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        return ch if isinstance(ch, discord.ForumChannel) else None

    async def _get_thread(self, guild: discord.Guild, thread_id: int) -> discord.Thread | None:
        thread = guild.get_thread(int(thread_id))
        if thread:
            return thread
        try:
            ch = await guild.fetch_channel(int(thread_id))
        except Exception:
            ch = None
        return ch if isinstance(ch, discord.Thread) else None

    async def _ensure_main_thread(self, guild: discord.Guild, forum: discord.ForumChannel):
        panel_thread_id = self._gi(guild.id, "seelsorge.panel_thread_id", 0)
        info_thread_id = self._gi(guild.id, "seelsorge.info_thread_id", 0)
        thread_id = panel_thread_id or info_thread_id
        thread = await self._get_thread(guild, thread_id) if thread_id else None

        if not thread:
            info_view = SeelsorgeInfoView(self, guild)
            res = await forum.create_thread(name=self._panel_thread_name(guild.id), view=info_view)
            thread = res.thread
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.panel_thread_id", int(thread.id))
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.info_thread_id", int(thread.id))
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.info_message_id", int(res.message.id))
            try:
                await res.message.pin()
            except Exception:
                pass

            panel_view = SeelsorgePanelView(self, guild)
            panel_msg = await thread.send(view=panel_view)
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.panel_message_id", int(panel_msg.id))
            return

        desired_name = self._panel_thread_name(guild.id)
        if desired_name and str(getattr(thread, "name", "")) != str(desired_name):
            try:
                await thread.edit(name=desired_name)
            except Exception:
                pass

        await self.settings.set_guild_override(self.db, guild.id, "seelsorge.panel_thread_id", int(thread.id))
        await self.settings.set_guild_override(self.db, guild.id, "seelsorge.info_thread_id", int(thread.id))

        info_message_id = self._gi(guild.id, "seelsorge.info_message_id", 0)
        info_view = SeelsorgeInfoView(self, guild)
        if info_message_id:
            try:
                msg = await thread.fetch_message(int(info_message_id))
                await msg.edit(view=info_view)
                try:
                    await msg.pin()
                except Exception:
                    pass
            except Exception:
                info_message_id = 0
        if not info_message_id:
            msg = await thread.send(view=info_view)
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.info_message_id", int(msg.id))
            try:
                await msg.pin()
            except Exception:
                pass

        panel_message_id = self._gi(guild.id, "seelsorge.panel_message_id", 0)
        panel_view = SeelsorgePanelView(self, guild)
        if panel_message_id:
            try:
                msg = await thread.fetch_message(int(panel_message_id))
                await msg.edit(view=panel_view)
            except Exception:
                panel_message_id = 0
        if not panel_message_id:
            msg = await thread.send(view=panel_view)
            await self.settings.set_guild_override(self.db, guild.id, "seelsorge.panel_message_id", int(msg.id))

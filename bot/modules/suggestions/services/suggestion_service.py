from __future__ import annotations

from datetime import datetime, timezone
import discord

from bot.core.perms import is_staff
from bot.modules.suggestions.formatting.suggestion_embeds import (
    build_suggestion_summary_view,
    build_suggestion_thread_info_container,
)
from bot.modules.suggestions.views.suggestion_panel import SuggestionPanelView

ALLOWED_STATUSES = {"pending", "accepted", "denied", "implemented", "reviewing"}


def _truncate(text: str, limit: int) -> str:
    if not text:
        return ""
    val = str(text)
    return val if len(val) <= limit else val[: limit - 3] + "..."


def _normalize_suggestion_row(row) -> dict | None:
    if not row:
        return None
    try:
        return {
            "id": int(row[0]),
            "guild_id": int(row[1]),
            "user_id": int(row[2]),
            "forum_channel_id": int(row[3]),
            "thread_id": int(row[4]),
            "summary_message_id": int(row[5]),
            "vote_message_id": int(row[6]),
            "title": str(row[7] or ""),
            "content": str(row[8] or ""),
            "status": str(row[9] or "pending"),
            "admin_response": str(row[10] or ""),
            "upvotes": int(row[11] or 0),
            "downvotes": int(row[12] or 0),
            "created_at": str(row[13] or ""),
            "updated_at": str(row[14] or ""),
        }
    except Exception:
        return None


class SuggestionService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._active_submissions: set[tuple[int, int]] = set()

    def _gi(self, guild_id: int, key: str, default: int = 0) -> int:
        return int(self.settings.get_guild_int(guild_id, key, default))

    def _g(self, guild_id: int, key: str, default=None):
        return self.settings.get_guild(guild_id, key, default)

    def _forum_channel_id(self, guild_id: int) -> int:
        return self._gi(guild_id, "suggestion.forum_channel_id", 0)

    def _panel_thread_name(self, guild_id: int) -> str:
        return str(
            self._g(guild_id, "suggestion.panel_thread_name", "💡 Vorschläge – Info") or "💡 Vorschläge – Info"
        )

    def _status_emoji(self, status: str) -> str:
        key = str(status or "pending").lower()
        mapping = {
            "pending": "🟠",
            "reviewing": "🧪",
            "accepted": "🟢",
            "denied": "🔴",
            "implemented": "🚀",
        }
        return mapping.get(key, "🟠")

    def _status_tag_name(self, status: str) -> str:
        key = str(status or "pending").lower()
        mapping = {
            "pending": "🟠 WARTEND",
            "reviewing": "🧪 IN PRÜFUNG",
            "accepted": "🟢 IN ARBEIT",
            "denied": "🔴 ABGELEHNT",
            "implemented": "🚀 UMGESETZT",
        }
        return mapping.get(key, "🟠 WARTEND")

    def _status_tag_names(self) -> set[str]:
        legacy = {"wartend", "in prüfung", "in arbeit", "abgelehnt", "umgesetzt"}
        current = {
            self._status_tag_name("pending"),
            self._status_tag_name("reviewing"),
            self._status_tag_name("accepted"),
            self._status_tag_name("denied"),
            self._status_tag_name("implemented"),
        }
        return {name.lower() for name in (legacy | current)}

    async def _ephemeral(self, interaction: discord.Interaction, text: str):
        try:
            await interaction.response.send_message(text, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(text, ephemeral=True)

    async def _resolve_forum(self, guild: discord.Guild) -> discord.ForumChannel | None:
        forum_id = self._forum_channel_id(guild.id)
        if not forum_id:
            return None
        ch = guild.get_channel(int(forum_id))
        if not ch:
            try:
                ch = await guild.fetch_channel(int(forum_id))
            except Exception:
                ch = None
        return ch if isinstance(ch, discord.ForumChannel) else None

    async def _get_thread(self, guild: discord.Guild, thread_id: int) -> discord.Thread | None:
        th = guild.get_thread(int(thread_id))
        if th:
            return th
        try:
            ch = await guild.fetch_channel(int(thread_id))
        except Exception:
            ch = None
        return ch if isinstance(ch, discord.Thread) else None

    async def _ensure_status_tag(self, forum: discord.ForumChannel, status: str) -> discord.ForumTag | None:
        name = self._status_tag_name(status)
        for tag in forum.available_tags:
            if str(tag.name).lower() == name.lower():
                return tag
        try:
            return await forum.create_tag(name=name)
        except Exception:
            return None

    async def _apply_status_tag(self, thread: discord.Thread, status: str):
        parent = getattr(thread, "parent", None)
        if not isinstance(parent, discord.ForumChannel):
            return
        tag = await self._ensure_status_tag(parent, status)
        if not tag:
            return

        keep = []
        status_names = self._status_tag_names()
        for t in list(getattr(thread, "applied_tags", []) or []):
            if str(t.name).lower() not in status_names:
                keep.append(t)
        if all(int(getattr(t, "id", 0)) != int(tag.id) for t in keep):
            keep.append(tag)
        try:
            await thread.edit(applied_tags=keep)
        except Exception:
            pass

    async def _apply_status_presentation(self, guild: discord.Guild, thread: discord.Thread, data: dict):
        status = str(data.get("status") or "pending").lower()
        title = str(data.get("title") or "").strip() or "Ohne Titel"
        sid = int(data.get("id") or 0)
        desired = _truncate(f"{self._status_emoji(status)} Vorschlag #{sid} · {title}", 100)
        if str(getattr(thread, "name", "")) != desired:
            try:
                await thread.edit(name=desired)
            except Exception:
                pass
        await self._apply_status_tag(thread, status)

    async def send_panel(self, interaction: discord.Interaction, forum: discord.ForumChannel | None = None):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Nur im Server nutzbar.")
        if not is_staff(self.settings, interaction.user):
            return await self._ephemeral(interaction, "Keine Rechte.")
        if forum:
            await self.settings.set_guild_override(self.db, interaction.guild.id, "suggestion.forum_channel_id", int(forum.id))
        forum_channel = forum or await self._resolve_forum(interaction.guild)
        if not forum_channel:
            return await self._ephemeral(interaction, "Suggestion-Forum nicht konfiguriert.")
        await interaction.response.defer(ephemeral=True)
        await self._ensure_panel_thread(interaction.guild, forum_channel)
        await self._refresh_suggestion_threads(interaction.guild)
        try:
            await interaction.edit_original_response(content="Suggestion-Panel aktualisiert.")
        except Exception:
            await interaction.followup.send("Suggestion-Panel aktualisiert.", ephemeral=True)

    async def _ensure_panel_thread(self, guild: discord.Guild, forum: discord.ForumChannel):
        thread_id = self._gi(guild.id, "suggestion.panel_thread_id", 0)
        message_id = self._gi(guild.id, "suggestion.panel_message_id", 0)
        thread = await self._get_thread(guild, thread_id) if thread_id else None

        if not thread:
            created = await forum.create_thread(
                name=_truncate(self._panel_thread_name(guild.id), 100),
                content="Info-Thread für Vorschläge",
            )
            thread = created.thread
            await self.settings.set_guild_override(self.db, guild.id, "suggestion.panel_thread_id", int(thread.id))
            message_id = 0

        desired_name = self._panel_thread_name(guild.id)
        if desired_name and str(getattr(thread, "name", "")) != str(desired_name):
            try:
                await thread.edit(name=desired_name[:100])
            except Exception:
                pass

        panel_view = SuggestionPanelView(self.settings, guild)
        if message_id:
            try:
                msg = await thread.fetch_message(int(message_id))
                await msg.edit(view=panel_view)
                return
            except Exception:
                message_id = 0
        if not message_id:
            msg = await thread.send(view=panel_view)
            await self.settings.set_guild_override(self.db, guild.id, "suggestion.panel_message_id", int(msg.id))
            try:
                await msg.pin()
            except Exception:
                pass

    def _build_thread_info_view(self, guild: discord.Guild) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(build_suggestion_thread_info_container(self.settings, guild))
        return view

    async def _refresh_thread_info_message(self, guild: discord.Guild, thread: discord.Thread):
        info_view = self._build_thread_info_view(guild)

        target = None
        try:
            pins = await thread.pins()
            for msg in pins:
                if not msg.author or not self.bot.user:
                    continue
                if int(msg.author.id) != int(self.bot.user.id):
                    continue
                if not msg.components:
                    continue
                target = msg
                break
        except Exception:
            target = None

        if target:
            try:
                await target.edit(view=info_view)
                return
            except Exception:
                pass

        try:
            msg = await thread.send(view=info_view)
            await msg.pin()
        except Exception:
            pass

    async def _refresh_suggestion_threads(self, guild: discord.Guild, limit: int = 2000):
        try:
            rows = await self.db.list_suggestions(guild.id, limit=limit)
        except Exception:
            return
        for row in rows:
            s = _normalize_suggestion_row(row)
            if not s:
                continue
            thread = await self._get_thread(guild, int(s["thread_id"]))
            if not thread:
                continue
            await self.refresh_suggestion_message(guild, int(s["id"]))

    async def submit_suggestion(self, interaction: discord.Interaction, title: str, content: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Nur im Server nutzbar.")
        if not self.settings.get_guild_bool(interaction.guild.id, "suggestion.enabled", True):
            return await self._ephemeral(interaction, "Vorschlags-System ist deaktiviert.")
        forum = await self._resolve_forum(interaction.guild)
        if not forum:
            return await self._ephemeral(interaction, "Suggestion-Forum nicht konfiguriert.")

        clean_title = _truncate((title or "").strip(), 120)
        clean_content = _truncate((content or "").strip(), 3800)
        if len(clean_title) < 4:
            return await self._ephemeral(interaction, "Titel ist zu kurz.")
        if len(clean_content) < 10:
            return await self._ephemeral(interaction, "Bitte beschreibe deinen Vorschlag genauer.")

        submit_key = (int(interaction.guild.id), int(interaction.user.id))
        if submit_key in self._active_submissions:
            return await self._ephemeral(interaction, "Dein Vorschlag wird schon erstellt. Bitte kurz warten.")
        self._active_submissions.add(submit_key)
        try:
            pending_tag = await self._ensure_status_tag(forum, "pending")
            thread_kwargs = {
                "name": _truncate(f"💡 {clean_title}", 100),
                "content": f"Vorschlag von <@{interaction.user.id}>",
            }
            if pending_tag:
                thread_kwargs["applied_tags"] = [pending_tag]
            created = await forum.create_thread(**thread_kwargs)
            thread = created.thread

            summary_data = {
                "id": 0,
                "user_id": int(interaction.user.id),
                "title": clean_title,
                "content": clean_content,
                "status": "pending",
                "admin_response": "",
                "upvotes": 0,
                "downvotes": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            summary_view = build_suggestion_summary_view(self.settings, interaction.guild, summary_data, interaction.user)
            summary_msg = await thread.send(view=summary_view)
            await self._refresh_thread_info_message(interaction.guild, thread)
            vote_msg = await thread.send("Stimme mit 👍 oder 👎 ab.")
            try:
                await vote_msg.add_reaction("👍")
                await vote_msg.add_reaction("👎")
            except Exception:
                pass

            suggestion_id = await self.db.create_suggestion(
                guild_id=int(interaction.guild.id),
                user_id=int(interaction.user.id),
                forum_channel_id=int(forum.id),
                thread_id=int(thread.id),
                summary_message_id=int(summary_msg.id),
                vote_message_id=int(vote_msg.id),
                title=clean_title,
                content=clean_content,
            )

            summary_data["id"] = int(suggestion_id)
            await self._apply_status_presentation(interaction.guild, thread, summary_data)
            await self.refresh_suggestion_message(interaction.guild, int(suggestion_id))
            await self._ephemeral(interaction, f"Vorschlag eingereicht. Thread: {thread.mention}")
            try:
                await self.logger.emit(
                    self.bot,
                    "suggestion_created",
                    {"suggestion_id": int(suggestion_id), "user_id": int(interaction.user.id), "thread_id": int(thread.id)},
                )
            except Exception:
                pass
        finally:
            self._active_submissions.discard(submit_key)

    async def refresh_suggestion_message(self, guild: discord.Guild, suggestion_id: int):
        row = await self.db.get_suggestion(int(suggestion_id))
        s = _normalize_suggestion_row(row)
        if not s:
            return
        thread = await self._get_thread(guild, int(s["thread_id"]))
        if not thread:
            return
        await self._apply_status_presentation(guild, thread, s)
        author = guild.get_member(int(s["user_id"]))
        if not author:
            try:
                author = await self.bot.fetch_user(int(s["user_id"]))
            except Exception:
                author = None

        view = build_suggestion_summary_view(self.settings, guild, s, author)
        try:
            msg = await thread.fetch_message(int(s["summary_message_id"]))
            await msg.edit(view=view)
        except Exception:
            try:
                msg = await thread.send(view=view)
                await self.db.update_suggestion_messages(int(s["id"]), int(msg.id), int(s["vote_message_id"]))
            except Exception:
                pass
        await self._refresh_thread_info_message(guild, thread)

    async def set_status(self, interaction: discord.Interaction, status: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Nur im Server nutzbar.")
        if not is_staff(self.settings, interaction.user):
            return await self._ephemeral(interaction, "Keine Rechte.")
        if not isinstance(interaction.channel, discord.Thread):
            return await self._ephemeral(interaction, "Nur im Vorschlags-Thread nutzbar.")

        status_key = str(status or "").strip().lower()
        if status_key not in ALLOWED_STATUSES:
            return await self._ephemeral(interaction, "Ungültiger Status.")

        row = await self.db.get_suggestion_by_thread(interaction.guild.id, interaction.channel.id)
        s = _normalize_suggestion_row(row)
        if not s:
            return await self._ephemeral(interaction, "Vorschlag nicht gefunden.")

        await self.db.set_suggestion_status(int(s["id"]), status_key)
        await self.refresh_suggestion_message(interaction.guild, int(s["id"]))
        await self._ephemeral(interaction, f"Status gesetzt: {status_key.title()}")

    async def set_admin_response(self, interaction: discord.Interaction, text: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await self._ephemeral(interaction, "Nur im Server nutzbar.")
        if not is_staff(self.settings, interaction.user):
            return await self._ephemeral(interaction, "Keine Rechte.")
        if not isinstance(interaction.channel, discord.Thread):
            return await self._ephemeral(interaction, "Nur im Vorschlags-Thread nutzbar.")
        row = await self.db.get_suggestion_by_thread(interaction.guild.id, interaction.channel.id)
        s = _normalize_suggestion_row(row)
        if not s:
            return await self._ephemeral(interaction, "Vorschlag nicht gefunden.")

        value = _truncate((text or "").strip(), 1800)
        await self.db.set_suggestion_admin_response(int(s["id"]), value if value else None)
        await self.refresh_suggestion_message(interaction.guild, int(s["id"]))
        await self._ephemeral(interaction, "Admin-Response aktualisiert.")

    async def handle_vote_reaction(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        emoji = str(getattr(payload.emoji, "name", "") or "")
        if emoji not in {"👍", "👎"}:
            return

        guild = self.bot.get_guild(int(payload.guild_id))
        if not guild or not self.bot.user or int(payload.user_id) == int(self.bot.user.id):
            return

        row = await self.db.get_suggestion_by_vote_message(int(payload.guild_id), int(payload.message_id))
        s = _normalize_suggestion_row(row)
        if not s:
            return

        thread = await self._get_thread(guild, int(s["thread_id"]))
        if not thread:
            return

        try:
            vote_msg = await thread.fetch_message(int(s["vote_message_id"]))
        except Exception:
            return

        # One-user-one-vote: when a user adds one side, remove the opposite reaction.
        try:
            member = guild.get_member(int(payload.user_id))
            if not member:
                member = await guild.fetch_member(int(payload.user_id))
            opposite = "👎" if emoji == "👍" else "👍"
            await vote_msg.remove_reaction(opposite, member)
        except Exception:
            pass

        upvotes = 0
        downvotes = 0
        for reaction in vote_msg.reactions:
            name = str(getattr(reaction.emoji, "name", reaction.emoji))
            if name not in {"👍", "👎"}:
                continue
            count = 0
            try:
                async for user in reaction.users(limit=None):
                    if user and not user.bot:
                        count += 1
            except Exception:
                count = max(0, int(reaction.count) - 1)
            if name == "👍":
                upvotes = count
            if name == "👎":
                downvotes = count

        await self.db.set_suggestion_votes(int(s["id"]), int(upvotes), int(downvotes))
        await self.refresh_suggestion_message(guild, int(s["id"]))

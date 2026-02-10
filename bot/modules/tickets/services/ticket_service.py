import re
import io
import json
import html as html_lib
import urllib.request
import asyncio
import discord
import uuid
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta

from bot.core.perms import is_staff
from bot.modules.tickets.views.summary_view import SummaryView
from bot.modules.tickets.views.rating_view import RatingView
from bot.modules.tickets.formatting.ticket_embeds import (
    build_summary_container,
    build_user_message_embed,
    build_dm_ticket_created_embed,
    build_dm_message_appended_embed,
    build_dm_staff_reply_embed,
    build_dm_ticket_closed_embed,
    build_dm_ticket_closed_container,
    build_dm_rating_thanks_embed,
    build_dm_ticket_added_embed,
    build_thread_status_embed,
    build_thread_rating_embed,
    build_dm_ticket_update_embed,
    build_ticket_log_embed,
    build_dm_ticket_forwarded_embed,
)
from bot.utils.emojis import em
from bot.utils.assets import Banners

_USER_ID_RE = re.compile(r"User-ID:\s*(\d{15,20})")


def _truncate(s: str, limit: int) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= limit else s[: limit - 3] + "..."

def _human_bytes(size: int | None) -> str:
    if size is None:
        return "0 B"
    try:
        size_int = int(size)
    except Exception:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    value = float(size_int)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{int(value)} B"

def _is_image_attachment(attachment: discord.Attachment) -> bool:
    ctype = str(getattr(attachment, "content_type", "") or "").lower()
    if ctype.startswith("image/"):
        return True
    name = str(getattr(attachment, "filename", "") or "").lower()
    return name.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"))

def _split_attachments(attachments, limit: int = 8) -> tuple[list[str], list[str]]:
    images: list[str] = []
    others: list[str] = []
    if not attachments:
        return images, others
    for att in list(attachments)[:limit]:
        try:
            url = att.url
        except Exception:
            continue
        if _is_image_attachment(att):
            images.append(url)
        else:
            others.append(url)
    return images, others


def _extract_component_text(components) -> str | None:
    if not components:
        return None

    def _walk(comp) -> str | None:
        content = getattr(comp, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        for child in getattr(comp, "children", []) or []:
            text = _walk(child)
            if text:
                return text
        for child in getattr(comp, "components", []) or []:
            text = _walk(child)
            if text:
                return text
        return None

    for comp in components:
        text = _walk(comp)
        if text:
            return text
    return None

def _clean_reply_snippet(text: str, limit: int = 140) -> str:
    if not text:
        return ""
    cleaned = str(text).replace("\n", " ").replace("»", "").strip()
    return _truncate(cleaned, limit)


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def parse_int_color(settings, guild_id: int | None = None) -> int:
    if guild_id:
        v = str(settings.get_guild(int(guild_id), "design.accent_color", "#B16B91") or "").replace("#", "").strip()
    else:
        v = str(settings.get("design.accent_color", "#B16B91") or "").replace("#", "").strip()
    try:
        return int(v, 16)
    except Exception:
        return 0xB16B91

def _extract_discord_ids(row) -> list[int]:
    ids: list[int] = []
    if not row:
        return ids

    for v in row:
        try:
            if isinstance(v, int):
                x = v
            elif isinstance(v, str) and v.isdigit():
                x = int(v)
            else:
                continue

            if 10**14 <= x <= 10**20:
                ids.append(x)
        except Exception:
            pass

    return ids

async def _ephemeral(interaction: discord.Interaction, text: str):
    try:
        await interaction.response.send_message(text, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(text, ephemeral=True)


def _normalize_ticket_row(guild_id: int, row):
    if not row:
        return None

    try:
        if len(row) >= 18:
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(guild_id),
                "user_id": int(row[1]) if row[1] is not None else 0,
                "forum_id": 0,
                "thread_id": int(row[2]),
                "summary_id": int(row[3]),
                "status": str(row[4]),
                "claimed_by": int(row[5]) if row[5] is not None else None,
                "category_key": str(row[6]) if row[6] is not None else None,
                "priority": int(row[7]) if row[7] is not None else None,
                "status_label": str(row[8]) if row[8] is not None else None,
                "escalated_level": int(row[9]) if row[9] is not None else None,
                "escalated_by": int(row[10]) if row[10] is not None else None,
                "created_at": row[11],
                "closed_at": row[12],
                "last_activity_at": row[13],
                "last_user_message_at": row[14],
                "last_staff_message_at": row[15],
                "first_staff_reply_at": row[16],
                "sla_breached_at": row[17],
            }
    except Exception:
        pass

    try:
        if len(row) >= 9 and int(row[1]) == int(guild_id):
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(row[1]),
                "user_id": int(row[2]),
                "forum_id": int(row[3]),
                "thread_id": int(row[4]),
                "summary_id": int(row[5]),
                "status": str(row[6]),
                "claimed_by": int(row[7]) if row[7] is not None else None,      
                "category_key": str(row[8]) if row[8] is not None else None,
            }
    except Exception:
        pass

    try:
        if len(row) >= 7:
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(guild_id),
                "user_id": int(row[1]),
                "forum_id": 0,
                "thread_id": int(row[2]),
                "summary_id": int(row[3]),
                "status": str(row[4]),
                "claimed_by": int(row[5]) if row[5] is not None else None,
                "category_key": str(row[6]) if row[6] is not None else None,
            }
    except Exception:
        pass

    try:
        if len(row) >= 6:
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(guild_id),
                "user_id": int(row[1]) if row[1] is not None else 0,
                "forum_id": 0,
                "thread_id": int(row[2]),
                "summary_id": int(row[3]),
                "status": str(row[4]),
                "claimed_by": int(row[5]) if row[5] is not None else None,
                "category_key": None,
            }
    except Exception:
        pass

    return None


def _normalize_open_ticket_row(row):
    if not row:
        return None
    try:
        if len(row) >= 6:
            return {
                "ticket_id": int(row[0]),
                "thread_id": int(row[1]),
                "summary_id": int(row[2]),
                "status": str(row[3]),
                "claimed_by": int(row[4]) if row[4] is not None else None,
                "category_key": str(row[5]) if row[5] is not None else None,
            }
    except Exception:
        pass
    try:
        if len(row) >= 2:
            return {"ticket_id": int(row[0]), "thread_id": int(row[1])}
    except Exception:
        pass
    return None


async def _resolve_user_id_from_thread(thread: discord.Thread, summary_message_id: int | None):
    if summary_message_id:
        try:
            msg = await thread.fetch_message(int(summary_message_id))
            if msg and msg.content:
                m = _USER_ID_RE.search(msg.content)
                if m:
                    return int(m.group(1))
        except Exception:
            pass

    try:
        starter = thread.starter_message
        if starter and starter.content:
            m = _USER_ID_RE.search(starter.content)
            if m:
                return int(m.group(1))
    except Exception:
        pass

    try:
        async for m in thread.history(limit=5, oldest_first=True):
            if m and m.content:
                mm = _USER_ID_RE.search(m.content)
                if mm:
                    return int(mm.group(1))
    except Exception:
        pass

    return None


class TicketService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _g(self, guild_id: int, key: str, default=None):
        return self.settings.get_guild(int(guild_id), key, default)

    def _gi(self, guild_id: int, key: str, default: int = 0) -> int:
        return self.settings.get_guild_int(int(guild_id), key, default)

    def _gb(self, guild_id: int, key: str, default: bool = False) -> bool:
        return self.settings.get_guild_bool(int(guild_id), key, default)

    def _priority_label(self, priority: int | None) -> str:
        mapping = {
            1: "Niedrig",
            2: "Normal",
            3: "Hoch",
            4: "Dringend",
        }
        return mapping.get(int(priority or 2), "Normal")

    async def _resolve_reply_meta(self, message: discord.Message) -> tuple[str | None, str | None]:
        ref = getattr(message, "reference", None)
        if not ref or not getattr(ref, "message_id", None):
            return None, None
        ref_msg = ref.resolved if isinstance(ref.resolved, discord.Message) else None
        if not ref_msg:
            try:
                ref_msg = await message.channel.fetch_message(int(ref.message_id))
            except Exception:
                return None, None
        author = None
        content = (ref_msg.content or "").strip()
        if ref_msg.embeds:
            emb = ref_msg.embeds[0]
            if not content and emb.description:
                content = emb.description
            if emb.author and emb.author.name:
                author = emb.author.name
        if not content:
            content = _extract_component_text(getattr(ref_msg, "components", None))
        if not author and ref_msg.author:
            author = getattr(ref_msg.author, "display_name", None) or getattr(ref_msg.author, "name", None)
        if not content and ref_msg.attachments:
            if any(_is_image_attachment(a) for a in ref_msg.attachments):
                content = "[Bild]"
            else:
                content = "[Anhang]"
        content = _clean_reply_snippet(content)
        return author, content if content else None

    async def _build_reply_line(self, message: discord.Message | None) -> str | None:
        if not message:
            return None
        author, snippet = await self._resolve_reply_meta(message)
        if not author and not snippet:
            return None
        if author and snippet:
            return f"↪ Antwort auf **{author}**: {snippet}"
        if author:
            return f"↪ Antwort auf **{author}**"
        return f"↪ Antwort auf: {snippet}"

    def _build_image_embed(self, guild: discord.Guild | None, author: discord.User | discord.Member | None, url: str):
        container = discord.ui.Container(accent_colour=parse_int_color(self.settings, guild.id if guild else None))
        try:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=url)
            container.add_item(gallery)
        except Exception:
            container.add_item(discord.ui.TextDisplay(url))
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)
        return view

    async def _get_ticket_log_channel(self, guild: discord.Guild | None):
        log_id = self._gi(guild.id, "ticket.log_channel_id") if guild else 0
        if not log_id:
            return None
        ch = guild.get_channel(log_id) if guild else None
        if not ch and self.bot:
            try:
                ch = await self.bot.fetch_channel(int(log_id))
            except Exception:
                ch = None
        return ch if ch and isinstance(ch, discord.abc.Messageable) else None

    async def _send_ticket_log(self, guild: discord.Guild | None, title: str, text: str,
                               ticket_id: int, thread: discord.Thread | None = None,
                               actor: discord.Member | None = None):
        ch = await self._get_ticket_log_channel(guild)
        if not ch:
            return
        view = build_ticket_log_embed(
            self.settings,
            guild,
            title,
            text,
            ticket_id=int(ticket_id),
            thread=thread,
            actor=actor,
        )
        try:
            await ch.send(view=view)
        except Exception:
            pass

    async def _notify_user_update(self, guild: discord.Guild | None, t: dict, title: str, text: str):
        try:
            gid = guild.id if guild else 0
            if not self._gb(gid, "ticket.notify_user_on_updates", True):
                return False, "disabled"
            uid = int(t["user_id"]) if t and t.get("user_id") else 0
            if not uid:
                return False, "user_id_missing"
            try:
                user = await self.bot.fetch_user(int(uid))
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
            banner_url = Banners.TICKETS_CLOSED if "geschlossen" in str(title or "").lower() else None
            view = build_dm_ticket_update_embed(self.settings, guild, title, text, banner_url=banner_url)
            try:
                await user.send(view=view)
                return True, None
            except Exception as e:
                return False, f"{type(e).__name__}: {e}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    async def _notify_user_forwarded(
        self,
        guild: discord.Guild | None,
        t: dict,
        role_name: str,
        reason: str | None,
    ):
        gid = guild.id if guild else 0
        if not self._gb(gid, "ticket.notify_user_on_updates", True):
            return False, "disabled"
        uid = int(t["user_id"]) if t and t.get("user_id") else 0
        if not uid:
            return False, "user_id_missing"
        try:
            user = await self.bot.fetch_user(int(uid))
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"
        view = build_dm_ticket_forwarded_embed(self.settings, guild, role_name, reason)
        try:
            await user.send(view=view)
            return True, None
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    async def _touch_ticket(self, ticket_id: int):
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            await self.db.set_last_activity(int(ticket_id), now_iso)
        except Exception:
            pass

    async def _resolve_ticket_context(self, interaction: discord.Interaction, allow_closed: bool = False):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return None, None, "Nur im Server nutzbar."

        if not is_staff(self.settings, interaction.user):
            return None, None, "Keine Rechte."

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return None, None, "Nur im Ticket-Thread."

        forum_id = self._gi(interaction.guild.id, "bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return None, None, "Nur im Ticket-Thread."

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return None, None, "Ticket nicht gefunden."

        if not allow_closed and str(t["status"]) == "closed":
            return None, None, "Ticket ist bereits geschlossen."

        return thread, t, None

    async def _get_participant_ids(self, ticket_id: int, fallback_user_id: int | None) -> list[int]:
        ids = []
        try:
            ids = await self.db.list_ticket_participants(int(ticket_id))
        except Exception:
            ids = []
        if fallback_user_id and int(fallback_user_id) not in ids:
            ids.append(int(fallback_user_id))
        return [int(i) for i in ids if i]

    async def get_participant_ids(self, ticket_id: int, fallback_user_id: int | None):
        return await self._get_participant_ids(ticket_id, fallback_user_id)

    async def get_ticket_from_thread(self, guild_id: int, thread_id: int):
        row = await self.db.get_ticket_by_thread(int(guild_id), int(thread_id))
        return _normalize_ticket_row(int(guild_id), row)

    async def _update_summary_controls(self, thread: discord.Thread, summary_message_id: int, ticket_id: int,
                                       claimed: bool, status: str | None = None):
        if not summary_message_id:
            return
        try:
            msg = await thread.fetch_message(int(summary_message_id))
            row = await self.db.get_ticket(int(ticket_id))
            t = _normalize_ticket_row(thread.guild.id, row)
            if not t:
                return
            container = await self._build_summary_container_for_ticket(thread.guild, t)
            if not container:
                return
            await msg.edit(
                view=SummaryView(
                    self,
                    ticket_id=int(ticket_id),
                    claimed=bool(claimed),
                    status=str(status or "open"),
                    container=container,
                )
            )
        except Exception:
            pass

    async def _build_summary_container_for_ticket(self, guild: discord.Guild, t: dict):
        if not guild or not t:
            return None
        user_id = int(t.get("user_id") or 0)
        if not user_id:
            return None

        member = guild.get_member(user_id)
        user = member
        if not user:
            try:
                user = await self.bot.fetch_user(int(user_id))
            except Exception:
                user = None
        if not user:
            user = SimpleNamespace(
                id=int(user_id),
                mention=f"<@{int(user_id)}>",
                created_at=datetime.now(timezone.utc),
            )

        category_key = str(t.get("category_key") or self._g(guild.id, "ticket.default_category", "allgemeine_frage"))
        cat_cfg = (self._g(guild.id, "categories", {}) or {}).get(category_key, {}) or {}
        cat_label = str(cat_cfg.get("label", category_key)).upper()

        created_at = _parse_iso(str(t.get("created_at") or "")) or datetime.now(timezone.utc)
        try:
            total = int(await self.db.get_ticket_count(int(user_id)))
        except Exception:
            total = 0

        return build_summary_container(
            self.settings,
            guild,
            user,
            member,
            _truncate(cat_label, 48),
            created_at=created_at,
            total_tickets=total,
            priority=t.get("priority"),
            status_label=t.get("status_label") or "🟢 OFFEN",
            escalated_level=t.get("escalated_level") or 0,
        )

    async def _notify_user_claim_state(self, guild: discord.Guild, thread: discord.Thread, t: dict,
                                       staff: discord.Member, claimed: bool):
        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(thread, t.get("summary_id"))
        if not uid:
            return False, "user_id_missing"

        try:
            user = await self.bot.fetch_user(int(uid))
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

        color = parse_int_color(self.settings, guild.id)
        arrow2 = em(self.settings, "arrow2", guild) or "➜"

        if claimed:
            title = "✅ 𑁉 TICKET ÜBERNOMMEN"
            desc = (
                f"{arrow2} Hey! Ich bin **{staff.display_name}** und übernehme dein Ticket. 💜\n\n"
                "┏`📩` - Antworte einfach hier per DM\n"
                "┗`🔁` - Ich hänge jede Nachricht automatisch ans Ticket."
            )
        else:
            title = "🔓 𑁉 TICKET FREIGEGEBEN"
            desc = (
                f"{arrow2} **{staff.display_name}** hat das Ticket freigegeben.\n\n"
                "┏`🟢` - Status: WIEDER OFFEN\n"
                "┗`📩` - Du kannst hier weiter per DM antworten."
            )

        container = discord.ui.Container(accent_colour=color)
        if claimed:
            try:
                gallery = discord.ui.MediaGallery()
                gallery.add_item(media=Banners.TICKETS_CLAIM)
                container.add_item(gallery)
                container.add_item(discord.ui.Separator())
            except Exception:
                pass
        container.add_item(discord.ui.TextDisplay(f"**{title}**\n{desc}"))
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)

        try:
            await user.send(view=view)
            return True, None
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def _dm_candidate_guilds(self, user_id: int) -> list[discord.Guild]:
        candidates = []
        for guild in list(self.bot.guilds):
            if not guild.get_member(int(user_id)):
                continue
            forum_id = self._gi(guild.id, "bot.forum_channel_id")
            if forum_id:
                candidates.append(guild)
        return candidates

    async def handle_dm(self, message: discord.Message):
        if message.author.bot:
            return
        await self.bot.wait_until_ready()
        try:
            await message.channel.typing()
        except Exception:
            pass

        candidates = self._dm_candidate_guilds(message.author.id)
        if not candidates:
            try:
                await message.author.send("Kein Ticket-System gefunden. Bitte nutze ein Server-Kommando.")
            except Exception:
                pass
            return
        if len(candidates) > 1:
            names = ", ".join([g.name for g in candidates[:5]])
            hint = "Bitte nutze ein Ticket-Kommando im Ziel-Server."
            if names:
                hint = f"Mehrere Server gefunden ({names}). Bitte nutze ein Ticket-Kommando im Ziel-Server."
            try:
                await message.author.send(hint)
            except Exception:
                pass
            return

        guild = candidates[0]
        guild_id = guild.id

        allow_multi = self._gb(guild_id, "ticket.allow_multiple_open_tickets_per_user", False)
        existing_row = await self.db.get_open_ticket_by_user(guild_id, message.author.id)
        existing = _normalize_open_ticket_row(existing_row)
        if not existing:
            participant_row = await self.db.get_open_ticket_by_participant(guild_id, message.author.id)
            existing = _normalize_open_ticket_row(participant_row)

        if existing and not allow_multi:
            thread = guild.get_thread(int(existing["thread_id"]))
            if not thread:
                try:
                    fetched = await self.bot.fetch_channel(int(existing["thread_id"]))
                    thread = fetched if isinstance(fetched, discord.Thread) else None
                except Exception:
                    thread = None

            if thread:
                await self._post_user_message(guild, thread, message.author, message.content, message.attachments, source_message=message)
                try:
                    now_iso = datetime.now(timezone.utc).isoformat()
                    await self.db.set_last_user_message(int(existing["ticket_id"]), now_iso)
                except Exception:
                    pass
                try:
                    await message.author.send(
                        view=build_dm_message_appended_embed(self.settings, guild, int(existing["ticket_id"]))
                    )
                except Exception:
                    pass

                await self.logger.emit(
                    self.bot,
                    "ticket_user_message_appended",
                    {"ticket_id": int(existing["ticket_id"]), "user_id": message.author.id},
                )
                return

        category_key = self._g(guild_id, "ticket.default_category", "allgemeine_frage")
        await self._create_ticket(guild, message, str(category_key))

    async def _create_ticket(self, guild: discord.Guild, dm_message: discord.Message, category_key: str):
        forum_id = self._gi(guild.id, "bot.forum_channel_id")
        forum = guild.get_channel(forum_id)
        if not isinstance(forum, discord.ForumChannel):
            try:
                fetched = await self.bot.fetch_channel(int(forum_id))
                forum = fetched if isinstance(fetched, discord.ForumChannel) else forum
            except Exception:
                pass
        if not isinstance(forum, discord.ForumChannel):
            try:
                await dm_message.author.send("Forum-Channel nicht gefunden. Bitte melde dich beim Team.")
            except Exception:
                pass
            return

        user = dm_message.author
        member = guild.get_member(user.id)
        total = await self.db.get_ticket_count(user.id)

        cat_cfg = (self._g(guild.id, "categories", {}) or {}).get(category_key, {}) or {}
        cat_label = str(cat_cfg.get("label", category_key)).upper()
        prefix = str(cat_cfg.get("thread_prefix", "🚑 •")).strip() or "🚑 •"
        if prefix == "•":
            prefix = "🚑 •"

        tag_id = int(cat_cfg.get("forum_tag_id", 0) or 0)
        applied_tags = []
        if tag_id:
            tag = discord.utils.get(forum.available_tags, id=tag_id)
            if tag:
                applied_tags.append(tag)

        created_at = datetime.now(timezone.utc)

        support_role_id = self._gi(guild.id, "bot.support_role_id")
        role_mention = f"<@&{support_role_id}>" if support_role_id else ""

        content_head = f"User-ID: {user.id}\n{role_mention}".strip()

        summary_container = build_summary_container(
            self.settings,
            guild,
            user,
            member,
            _truncate(cat_label, 48),
            created_at=created_at,
            total_tickets=int(total),
            priority=2,
            status_label="🟢 OFFEN",
            escalated_level=0,
        )

        view = SummaryView(self, ticket_id=0, status="open", container=summary_container)

        thread_name = f"{prefix} {user.display_name}"
        try:
            created = await forum.create_thread(
                name=_truncate(thread_name, 100),
                content=content_head,
                view=view,
                applied_tags=applied_tags,
            )
        except Exception as e:
            try:
                await dm_message.author.send("Ticket konnte nicht erstellt werden. Bitte melde dich beim Team.")
            except Exception:
                pass
            try:
                await self.logger.emit(self.bot, "ticket_create_failed", {"user_id": dm_message.author.id, "error": f"{type(e).__name__}: {e}"})
            except Exception:
                pass
            return

        thread = created.thread
        msg = created.message

        ticket_id = await self.db.create_ticket(
            guild_id=guild.id,
            user_id=user.id,
            forum_channel_id=forum.id,
            thread_id=thread.id,
            summary_message_id=msg.id,
            category_key=category_key,
        )
        await self.db.add_ticket_participant(int(ticket_id), int(user.id), added_by=None)

        view.ticket_id = int(ticket_id)
        try:
            await msg.edit(view=view)
        except Exception:
            pass

        await self._post_user_message(guild, thread, user, dm_message.content, dm_message.attachments, source_message=dm_message)
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            await self.db.set_last_user_message(int(ticket_id), now_iso)
        except Exception:
            pass

        try:
            await user.send(view=build_dm_ticket_created_embed(self.settings, guild, int(ticket_id), created_at))
        except Exception:
            pass

        await self.logger.emit(
            self.bot,
            "ticket_created",
            {"ticket_id": int(ticket_id), "user_id": user.id, "thread_id": thread.id, "category": category_key},
        )

    async def _post_user_message(self, guild: discord.Guild, thread: discord.Thread, user: discord.User, content: str, attachments, source_message: discord.Message | None = None):
        text = (content or "").strip()
        reply_line = await self._build_reply_line(source_message)

        images, other_links = _split_attachments(attachments, limit=8)
        if other_links:
            links = "\n".join(other_links)
            if links:
                text = (text + "\n\n" + links).strip()
        if reply_line:
            text = f"{reply_line}\n\n{text}".strip()

        text = _truncate(text, 3500) if text else " "
        view = build_user_message_embed(self.settings, guild, user, text)
        await thread.send(view=view)

        for url in images:
            try:
                await thread.send(view=self._build_image_embed(guild, user, url))
            except Exception:
                pass

    async def handle_staff_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild or not isinstance(message.author, discord.Member):
            return


        if not is_staff(self.settings, message.author):
            return

        if not isinstance(message.channel, discord.Thread):
            return

        forum_id = self._gi(message.guild.id, "bot.forum_channel_id")
        parent = getattr(message.channel, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return

        row = await self.db.get_ticket_by_thread(message.guild.id, message.channel.id)
        t = _normalize_ticket_row(message.guild.id, row)
        if not t:
            return

        if str(t["status"]) == "closed":
            return

        text = (message.content or "").strip()
        reply_line = await self._build_reply_line(message)

        images: list[str] = []
        if self._gb(message.guild.id, "ticket.mirror_staff_attachments", True) and message.attachments:
            images, other_links = _split_attachments(message.attachments, limit=8)
            if other_links:
                links = "\n".join(other_links)
                if links:
                    text = (text + "\n\n" + links).strip()

        text = _truncate(text, 3500) if text else " "
        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(message.channel, t.get("summary_id"))

        if not uid:
            await self.logger.emit(self.bot, "ticket_staff_reply_failed_no_user", {"ticket_id": int(t["ticket_id"]), "thread_id": int(t["thread_id"])})
            return

        participant_ids = await self._get_participant_ids(int(t["ticket_id"]), uid)
        if int(uid) not in participant_ids:
            participant_ids.append(int(uid))

        dm_ok = False
        dm_error = None
        view = build_dm_staff_reply_embed(self.settings, message.guild, message.author, int(t["ticket_id"]), text, reply_line=reply_line)
        for pid in participant_ids:
            try:
                user = await self.bot.fetch_user(int(pid))
                await user.send(view=view)
                for url in images:
                    try:
                        await user.send(view=self._build_image_embed(message.guild, message.author, url))
                    except Exception:
                        pass
                dm_ok = True
            except Exception as e:
                dm_error = f"{type(e).__name__}: {e}"

        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            await self.db.set_last_staff_message(int(t["ticket_id"]), now_iso)
        except Exception:
            pass

        await self.logger.emit(
            self.bot,
            "ticket_staff_reply",
            {"ticket_id": int(t["ticket_id"]), "staff_id": message.author.id, "user_id": int(uid), "dm_ok": dm_ok, "dm_error": dm_error, "recipients": participant_ids[:25]},
        )

        try:
            if dm_ok:
                await message.add_reaction(em(self.settings, "green", message.guild) or "✅")
            else:
                await message.add_reaction(em(self.settings, "red", message.guild) or "❌")
        except Exception:
            pass

    async def toggle_claim(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self._gi(interaction.guild.id, "bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        if str(t["status"]) == "closed":
            return await _ephemeral(interaction, "Ticket ist bereits geschlossen.")

        ticket_id = int(t["ticket_id"])
        claimed_by = t.get("claimed_by")

        if claimed_by and int(claimed_by) != interaction.user.id:
            return await _ephemeral(interaction, f"Schon geclaimed von <@{claimed_by}>.")

        if claimed_by and int(claimed_by) == interaction.user.id:
            await self.db.set_claim(ticket_id, None)
            await self._touch_ticket(int(ticket_id))

            try:
                view = build_thread_status_embed(
                    self.settings,
                    interaction.guild,
                    "🔓 Ticket freigegeben",
                    f"{interaction.user.mention} kümmert sich nicht mehr um dieses Ticket.",
                    interaction.user
                )
                await thread.send(view=view)
            except Exception:
                pass

            dm_ok, dm_error = await self._notify_user_claim_state(interaction.guild, thread, t, interaction.user,
                                                                  claimed=False)
            await self._update_summary_controls(thread, int(t.get("summary_id") or 0), ticket_id, claimed=False, status="open")

            await _ephemeral(interaction, "Ticket freigegeben.")
            await self.logger.emit(self.bot, "ticket_released", {
                "ticket_id": ticket_id,
                "staff_id": interaction.user.id,
                "dm_ok": dm_ok,
                "dm_error": dm_error
            })
            return

        await self.db.set_claim(ticket_id, interaction.user.id)
        await self._touch_ticket(int(ticket_id))

        try:
            arrow2 = em(self.settings, "arrow2", interaction.guild) or "➜"

            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "✅ 𑁉 TICKET ÜBERNOMMEN",
                (
                    f"{arrow2} Hey! Ich bin {interaction.user.mention} und übernehme dein Ticket. 💜\n\n"
                    "┏`📩` - Schreib einfach hier rein\n"
                    "┗`🧾` - Ich kümmere mich jetzt darum."
                ),
                interaction.user,
                banner_url=Banners.TICKETS_CLAIM,
            )

            await thread.send(view=view)
        except Exception:
            pass

        dm_ok, dm_error = await self._notify_user_claim_state(interaction.guild, thread, t, interaction.user,
                                                              claimed=True)
        await self._update_summary_controls(thread, int(t.get("summary_id") or 0), ticket_id, claimed=True, status="claimed")

        await _ephemeral(interaction, "Ticket geclaimed.")
        await self.logger.emit(self.bot, "ticket_claimed", {
            "ticket_id": ticket_id,
            "staff_id": interaction.user.id,
            "dm_ok": dm_ok,
            "dm_error": dm_error
        })

    async def post_team_note(self, interaction: discord.Interaction, text: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self._gi(interaction.guild.id, "bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        note_text = _truncate((text or "").strip(), 3500) if text else " "

        try:
            view = build_thread_status_embed(self.settings, interaction.guild, "📝 TEAM-NOTIZ", note_text, interaction.user)
            await thread.send(view=view)
        except Exception:
            pass

        await self._touch_ticket(int(t["ticket_id"]))

        await _ephemeral(interaction, "Notiz gespeichert.")
        await self.logger.emit(self.bot, "ticket_note", {"ticket_id": int(t["ticket_id"]), "staff_id": interaction.user.id})

    async def add_participant(self, interaction: discord.Interaction, user: discord.User):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self._gi(interaction.guild.id, "bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        t = await self.get_ticket_from_thread(interaction.guild.id, thread.id)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        if str(t["status"]) == "closed":
            return await _ephemeral(interaction, "Ticket ist bereits geschlossen.")

        await self.db.add_ticket_participant(int(t["ticket_id"]), int(user.id), added_by=int(interaction.user.id))

        try:
            await thread.add_user(user)
        except Exception:
            pass

        try:
            arrow2 = em(self.settings, "arrow2", interaction.guild) or "➜"

            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "➕ 𑁉 USER HINZUGEFÜGT",
                (
                    f"{arrow2} {user.mention} wurde zum Ticket hinzugefügt.\n\n"
                    "┏`📩` - Er/Sie kann jetzt hier schreiben\n"
                    "┗`🔁` - Antworten kommen künftig per DM."
                ),
                interaction.user,
            )

            await thread.send(view=view)
        except Exception:
            pass

        try:
            dm_view = build_dm_ticket_added_embed(self.settings, interaction.guild, int(t["ticket_id"]), interaction.user)
            await user.send(view=dm_view)
        except Exception:
            pass

        await self._touch_ticket(int(t["ticket_id"]))

        await _ephemeral(interaction, f"{user.mention} hinzugefügt.")
        await self.logger.emit(
            self.bot,
            "ticket_participant_added",
            {"ticket_id": int(t["ticket_id"]), "staff_id": interaction.user.id, "user_id": int(user.id)},
        )

    async def dashboard_add_participant(self, guild: discord.Guild, thread: discord.Thread, actor: discord.Member, user: discord.User):
        t = await self.get_ticket_from_thread(guild.id, thread.id)
        if not t:
            return False, "ticket_not_found"
        if str(t["status"]) == "closed":
            return False, "ticket_closed"

        await self.db.add_ticket_participant(int(t["ticket_id"]), int(user.id), added_by=int(actor.id))
        await self._touch_ticket(int(t["ticket_id"]))

        try:
            await thread.add_user(user)
        except Exception:
            pass

        try:
            view = build_thread_status_embed(
                self.settings,
                guild,
                "➕ User hinzugefügt",
                f"{user.mention} wurde zum Ticket hinzugefügt und erhält künftig Antworten per DM.",
                actor,
            )
            await thread.send(view=view)
        except Exception:
            pass

        try:
            dm_view = build_dm_ticket_added_embed(self.settings, guild, int(t["ticket_id"]), actor)
            await user.send(view=dm_view)
        except Exception:
            pass

        await self.logger.emit(
            self.bot,
            "ticket_participant_added",
            {"ticket_id": int(t["ticket_id"]), "staff_id": actor.id, "user_id": int(user.id), "source": "dashboard"},
        )
        return True, None

    async def dashboard_set_claim(self, guild: discord.Guild, thread: discord.Thread, actor: discord.Member, claimed: bool):
        t = await self.get_ticket_from_thread(guild.id, thread.id)
        if not t:
            return False, "ticket_not_found"
        if str(t["status"]) == "closed":
            return False, "ticket_closed"

        ticket_id = int(t["ticket_id"])
        claimed_by = t.get("claimed_by")

        if claimed and claimed_by and int(claimed_by) != actor.id:
            return False, "claimed_by_other"

        if claimed:
            await self.db.set_claim(ticket_id, actor.id)
            await self._touch_ticket(int(ticket_id))
            title = "✅ Ticket übernommen"
            body = f"Hey! Ich bin {actor.mention} und werde dir heute helfen."
        else:
            await self.db.set_claim(ticket_id, None)
            await self._touch_ticket(int(ticket_id))
            title = "🔓 Ticket freigegeben"
            body = f"{actor.mention} kümmert sich nicht mehr um dieses Ticket."

        try:
            view = build_thread_status_embed(
                self.settings,
                guild,
                title,
                body,
                actor,
                banner_url=Banners.TICKETS_CLAIM if claimed else None,
            )
            await thread.send(view=view)
        except Exception:
            pass

        try:
            dm_ok, dm_error = await self._notify_user_claim_state(guild, thread, t, actor, claimed=claimed)
        except Exception:
            dm_ok, dm_error = False, "dm_failed"

        await self._update_summary_controls(thread, int(t.get("summary_id") or 0), ticket_id, claimed=claimed, status="claimed" if claimed else "open")

        await self.logger.emit(
            self.bot,
            "ticket_claimed" if claimed else "ticket_released",
            {"ticket_id": ticket_id, "staff_id": actor.id, "dm_ok": dm_ok, "dm_error": dm_error, "source": "dashboard"},
        )
        return True, None

    async def dashboard_close_ticket(self, guild: discord.Guild, thread: discord.Thread, actor: discord.Member, reason: str | None = None):
        t = await self.get_ticket_from_thread(guild.id, thread.id)
        if not t:
            return False, "ticket_not_found"
        if str(t["status"]) == "closed":
            return False, "ticket_closed"

        await self.db.close_ticket(int(t["ticket_id"]))
        closed_at = datetime.now(timezone.utc)

        rating_enabled = self._gb(guild.id, "ticket.rating_enabled", True)

        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(thread, t.get("summary_id"))

        dm_ok = False
        dm_error = None
        transcript_ok = False
        transcript_error = None
        transcript_url = None
        transcript_ok = False
        transcript_error = None
        transcript_url = None

        if uid:
            try:
                user = await self.bot.fetch_user(int(uid))
                if rating_enabled:
                    container = build_dm_ticket_closed_container(
                        self.settings, guild, int(t["ticket_id"]), closed_at, rating_enabled
                    )
                    await user.send(view=RatingView(self, int(t["ticket_id"]), container=container))
                else:
                    await user.send(
                        view=build_dm_ticket_closed_embed(
                            self.settings, guild, int(t["ticket_id"]), closed_at, rating_enabled
                        )
                    )
                dm_ok = True
                transcript_ok, transcript_error, transcript_url = await self._send_transcript_dm(user, thread, t)
                transcript_ok, transcript_error, transcript_url = await self._send_transcript_dm(user, thread, t)
            except Exception as e:
                dm_ok = False
                dm_error = f"{type(e).__name__}: {e}"
        else:
            dm_ok = False
            dm_error = "user_id_missing"

        status_text = "Ticket wurde geschlossen und archiviert."
        if not dm_ok:
            status_text += "\n\n⚠️ User konnte nicht per DM erreicht werden."
        elif transcript_ok:
            status_text += "\n\n🧾 Transcript wurde per DM gesendet."
        elif transcript_error:
            status_text += "\n\n⚠️ Transcript konnte nicht per DM gesendet werden."
        elif transcript_ok:
            status_text += "\n\n🧾 Transcript wurde per DM gesendet."
        elif transcript_error:
            status_text += "\n\n⚠️ Transcript konnte nicht per DM gesendet werden."
        try:
            view = build_thread_status_embed(
                self.settings,
                guild,
                "🔒 Ticket geschlossen",
                status_text,
                actor,
                banner_url=Banners.TICKETS_CLOSED,
            )
            await thread.send(view=view)
        except Exception:
            pass

        try:
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass

        await self._update_summary_controls(
            thread,
            int(t.get("summary_id") or 0),
            int(t["ticket_id"]),
            claimed=False,
            status="closed",
        )

        await self._send_ticket_log(
            guild,
            "Ticket geschlossen",
            status_text,
            int(t["ticket_id"]),
            thread=thread,
            actor=actor,
        )

        await self.logger.emit(
            self.bot,
            "ticket_closed",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": actor.id,
                "user_id": int(uid) if uid else int(t.get("user_id") or 0),     
                "dm_ok": dm_ok,
                "dm_error": dm_error,
                "transcript_ok": transcript_ok,
                "transcript_error": transcript_error,
                "transcript_url": transcript_url,
                "reason": reason if reason else None,
                "source": "dashboard",
            },
        )
        return True, None

    async def close_ticket(self, interaction: discord.Interaction, reason: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self._gi(interaction.guild.id, "bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        if str(t["status"]) == "closed":
            return await _ephemeral(interaction, "Ticket ist bereits geschlossen.")

        await self.db.close_ticket(int(t["ticket_id"]))
        closed_at = datetime.now(timezone.utc)

        rating_enabled = self._gb(interaction.guild.id, "ticket.rating_enabled", True)

        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(thread, t.get("summary_id"))

        dm_ok = False
        dm_error = None

        if uid:
            try:
                user = await self.bot.fetch_user(int(uid))
                if rating_enabled:
                    container = build_dm_ticket_closed_container(
                        self.settings, interaction.guild, int(t["ticket_id"]), closed_at, rating_enabled
                    )
                    await user.send(view=RatingView(self, int(t["ticket_id"]), container=container))
                else:
                    await user.send(
                        view=build_dm_ticket_closed_embed(
                            self.settings, interaction.guild, int(t["ticket_id"]), closed_at, rating_enabled
                        )
                    )
                dm_ok = True
            except Exception as e:
                dm_ok = False
                dm_error = f"{type(e).__name__}: {e}"
        else:
            dm_ok = False
            dm_error = "user_id_missing"

        status_text = "Ticket wurde geschlossen und archiviert."
        if not dm_ok:
            status_text += "\n\n⚠️ User konnte nicht per DM erreicht werden."
        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "🔒 Ticket geschlossen",
                status_text,
                interaction.user,
                banner_url=Banners.TICKETS_CLOSED,
            )
            await thread.send(view=view)
        except Exception:
            pass

        try:
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass

        await self._update_summary_controls(
            thread,
            int(t.get("summary_id") or 0),
            int(t["ticket_id"]),
            claimed=False,
            status="closed",
        )

        await self._send_ticket_log(
            interaction.guild,
            "Ticket geschlossen",
            status_text,
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, "Ticket geschlossen." + ("" if dm_ok else " (User DM nicht möglich)"))

        await self.logger.emit(
            self.bot,
            "ticket_closed",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "user_id": int(uid) if uid else int(t.get("user_id") or 0),     
                "dm_ok": dm_ok,
                "dm_error": dm_error,
                "transcript_ok": transcript_ok,
                "transcript_error": transcript_error,
                "transcript_url": transcript_url,
                "reason": reason if reason else None,
            },
        )

    async def forward_ticket(self, interaction: discord.Interaction, role: discord.Role, reason: str | None):
        thread, t, err = await self._resolve_ticket_context(interaction)
        if err:
            return await _ephemeral(interaction, err)

        reason_text = _truncate((reason or "").strip(), 500) if reason else ""
        arrow2 = em(self.settings, "arrow2", interaction.guild) or "➜"

        body = (
            f"{arrow2} Das Ticket wurde weitergeleitet.\n\n"
            f"┏`🎯` - Ziel: {role.mention}\n"
            f"┗`📝` - Grund: {reason_text or '—'}"
        )
        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "📨 Ticket weitergeleitet",
                body,
                interaction.user,
            )
            await thread.send(view=view)
            await thread.send(role.mention)
        except Exception:
            pass

        dm_ok, dm_error = await self._notify_user_forwarded(
            interaction.guild,
            t,
            role.name,
            reason_text or None,
        )

        await self._send_ticket_log(
            interaction.guild,
            "Ticket weitergeleitet",
            f"Rolle: {role.mention}\nGrund: {reason_text or '—'}",
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, f"Ticket weitergeleitet an {role.mention}.")
        await self.logger.emit(
            self.bot,
            "ticket_forwarded",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "role_id": int(role.id),
                "reason": reason_text or None,
                "dm_ok": dm_ok,
                "dm_error": dm_error,
            },
        )

    async def reopen_ticket(self, interaction: discord.Interaction):
        thread, t, err = await self._resolve_ticket_context(interaction, allow_closed=True)
        if err:
            return await _ephemeral(interaction, err)

        if str(t["status"]) != "closed":
            return await _ephemeral(interaction, "Ticket ist bereits offen.")

        await self.db.reopen_ticket(int(t["ticket_id"]))
        await self._touch_ticket(int(t["ticket_id"]))

        try:
            await thread.edit(archived=False, locked=False)
        except Exception:
            pass

        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "🔓 Ticket wieder geöffnet",
                f"{interaction.user.mention} hat das Ticket wieder geöffnet.",
                interaction.user,
            )
            await thread.send(view=view)
        except Exception:
            pass

        await self._update_summary_controls(thread, int(t.get("summary_id") or 0), int(t["ticket_id"]), claimed=False, status="open")

        dm_ok, dm_error = await self._notify_user_update(
            interaction.guild,
            t,
            "Ticket wieder geöffnet",
            "Dein Ticket wurde wieder geöffnet. Du kannst hier weiter schreiben."
        )

        await self._send_ticket_log(
            interaction.guild,
            "Ticket wieder geöffnet",
            f"Von {interaction.user.mention}.",
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, "Ticket wieder geöffnet.")
        await self.logger.emit(
            self.bot,
            "ticket_reopened",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "dm_ok": dm_ok,
                "dm_error": dm_error,
            },
        )

    async def set_status_label(self, interaction: discord.Interaction, label: str):
        thread, t, err = await self._resolve_ticket_context(interaction)
        if err:
            return await _ephemeral(interaction, err)

        label = _truncate((label or "").strip(), 32) if label else ""
        if not label:
            return await _ephemeral(interaction, "Bitte einen Status angeben.")

        await self.db.set_status_label(int(t["ticket_id"]), label)
        await self._touch_ticket(int(t["ticket_id"]))

        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "🏷️ Status geändert",
                f"Neuer Status: **{label}**",
                interaction.user,
            )
            await thread.send(view=view)
        except Exception:
            pass

        dm_ok, dm_error = await self._notify_user_update(
            interaction.guild,
            t,
            "Status geändert",
            f"Neuer Status: **{label}**"
        )

        await self._send_ticket_log(
            interaction.guild,
            "Status geändert",
            f"Neuer Status: **{label}**",
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, "Status gespeichert.")
        await self.logger.emit(
            self.bot,
            "ticket_status_changed",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "status_label": label,
                "dm_ok": dm_ok,
                "dm_error": dm_error,
            },
        )

    async def set_priority(self, interaction: discord.Interaction, priority: int):
        thread, t, err = await self._resolve_ticket_context(interaction)
        if err:
            return await _ephemeral(interaction, err)

        priority = int(priority)
        if priority < 1 or priority > 4:
            return await _ephemeral(interaction, "Priority muss zwischen 1 und 4 liegen.")

        await self.db.set_priority(int(t["ticket_id"]), priority)
        await self._touch_ticket(int(t["ticket_id"]))

        label = self._priority_label(priority)
        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "🚦 Priorität geändert",
                f"Neue Priorität: **{label}**",
                interaction.user,
            )
            await thread.send(view=view)
        except Exception:
            pass

        dm_ok, dm_error = await self._notify_user_update(
            interaction.guild,
            t,
            "Priorität geändert",
            f"Neue Priorität: **{label}**"
        )

        await self._send_ticket_log(
            interaction.guild,
            "Priorität geändert",
            f"Neue Priorität: **{label}**",
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, "Priorität gespeichert.")
        await self.logger.emit(
            self.bot,
            "ticket_priority_changed",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "priority": int(priority),
                "dm_ok": dm_ok,
                "dm_error": dm_error,
            },
        )

    async def escalate_ticket(self, interaction: discord.Interaction, level: int, reason: str | None):
        thread, t, err = await self._resolve_ticket_context(interaction)
        if err:
            return await _ephemeral(interaction, err)

        level = int(level)
        if level < 1 or level > 5:
            return await _ephemeral(interaction, "Eskalation-Level muss zwischen 1 und 5 liegen.")

        await self.db.set_escalation(int(t["ticket_id"]), level, int(interaction.user.id))
        await self._touch_ticket(int(t["ticket_id"]))

        note = _truncate((reason or "").strip(), 500) if reason else ""
        body = f"Eskalations-Level: **{level}**"
        if note:
            body += f"\n\n{note}"

        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "⚠️ Ticket eskaliert",
                body,
                interaction.user,
            )
            await thread.send(view=view)
        except Exception:
            pass

        esc_role_id = self._gi(interaction.guild.id, "ticket.escalation_role_id")
        if esc_role_id:
            try:
                await thread.send(f"<@&{esc_role_id}>")
            except Exception:
                pass

        dm_ok, dm_error = await self._notify_user_update(
            interaction.guild,
            t,
            "Ticket eskaliert",
            body
        )

        await self._send_ticket_log(
            interaction.guild,
            "Ticket eskaliert",
            body,
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, "Ticket eskaliert.")
        await self.logger.emit(
            self.bot,
            "ticket_escalated",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "level": int(level),
                "reason": note if note else None,
                "dm_ok": dm_ok,
                "dm_error": dm_error,
            },
        )

    async def change_category(self, interaction: discord.Interaction, category_key: str):
        thread, t, err = await self._resolve_ticket_context(interaction)
        if err:
            return await _ephemeral(interaction, err)

        category_key = (category_key or "").strip()
        categories = self._g(interaction.guild.id, "categories", {}) or {}
        if category_key not in categories:
            return await _ephemeral(interaction, "Kategorie nicht gefunden.")

        cat_cfg = categories.get(category_key, {}) or {}
        cat_label = str(cat_cfg.get("label", category_key)).upper()
        prefix = str(cat_cfg.get("thread_prefix", "🚑 •")).strip() or "🚑 •"
        if prefix == "•":
            prefix = "🚑 •"

        tag_id = int(cat_cfg.get("forum_tag_id", 0) or 0)
        applied_tags = []
        if tag_id:
            tag = discord.utils.get(thread.parent.available_tags, id=tag_id) if thread.parent else None
            if tag:
                applied_tags.append(tag)

        base_name = thread.name
        if "•" in base_name:
            base_name = base_name.split("•", 1)[-1].strip()
        try:
            await thread.edit(
                name=_truncate(f"{prefix} {base_name}", 100),
                applied_tags=applied_tags,
            )
        except Exception:
            pass

        await self.db.set_category_key(int(t["ticket_id"]), category_key)
        await self._touch_ticket(int(t["ticket_id"]))

        try:
            view = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "🏷️ Kategorie geändert",
                f"Neue Kategorie: **{_truncate(cat_label, 48)}**",
                interaction.user,
            )
            await thread.send(view=view)
        except Exception:
            pass

        dm_ok, dm_error = await self._notify_user_update(
            interaction.guild,
            t,
            "Kategorie geändert",
            f"Neue Kategorie: **{_truncate(cat_label, 48)}**"
        )

        await self._send_ticket_log(
            interaction.guild,
            "Kategorie geändert",
            f"Neue Kategorie: **{_truncate(cat_label, 48)}**",
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await _ephemeral(interaction, "Kategorie geändert.")
        await self.logger.emit(
            self.bot,
            "ticket_category_changed",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "category": category_key,
                "dm_ok": dm_ok,
                "dm_error": dm_error,
            },
        )

    async def send_transcript(self, interaction: discord.Interaction, channel: discord.abc.Messageable | None = None):
        thread, t, err = await self._resolve_ticket_context(interaction, allow_closed=True)
        if err:
            return await _ephemeral(interaction, err)

        await _ephemeral(interaction, "Erstelle Transcript...")

        html_data = await self._render_html_transcript(thread, t)
        filename = f"ticket-{int(t['ticket_id'])}-transcript.html"
        target = channel or await self._get_ticket_log_channel(interaction.guild) or thread
        try:
            await target.send(file=discord.File(io.BytesIO(html_data), filename=filename))
        except Exception:
            pass

        guild_id = int(t.get("guild_id") or (interaction.guild.id if interaction.guild else 0) or 0)
        upload_url = await self._upload_transcript(guild_id, filename, html_data)
        if upload_url:
            try:
                await thread.send(f"Transcript: {upload_url}")
            except Exception:
                pass

        await self._send_ticket_log(
            interaction.guild,
            "Transcript erstellt",
            f"Transcript wurde generiert ({filename}).",
            int(t["ticket_id"]),
            thread=thread,
            actor=interaction.user,
        )

        await self.logger.emit(
            self.bot,
            "ticket_transcript_created",
            {"ticket_id": int(t["ticket_id"]), "staff_id": interaction.user.id},
        )

    async def _render_html_transcript(self, thread: discord.Thread, t: dict) -> bytes:
        title = f"Ticket #{int(t['ticket_id'])}"
        header = (
            f"{title} • Status: {t.get('status')} • Priority: {self._priority_label(t.get('priority'))}"
        )
        messages = []
        try:
            async for msg in thread.history(limit=None, oldest_first=True):
                ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                author_name = getattr(msg.author, "display_name", str(msg.author))
                author_tag = str(msg.author)
                avatar = ""
                try:
                    avatar = str(msg.author.display_avatar.url)
                except Exception:
                    avatar = ""
                role_color = "#ffffff"
                try:
                    if isinstance(msg.author, discord.Member) and msg.author.color:
                        role_color = f"#{msg.author.color.value:06x}"
                except Exception:
                    role_color = "#ffffff"
                content = html_lib.escape(msg.content or "").replace("\n", "<br>")
                attachment_bits = []
                for a in msg.attachments:
                    filename = html_lib.escape(a.filename or "file")
                    is_image = False
                    try:
                        if a.content_type and a.content_type.startswith("image/"):
                            is_image = True
                    except Exception:
                        is_image = False
                    if not is_image:
                        lower = (a.filename or "").lower()
                        if lower.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")):
                            is_image = True
                    if is_image:
                        attachment_bits.append(
                            f"<div class='attachment image'><a href='{a.url}'><img src='{a.url}' alt='{filename}'></a></div>"
                        )
                    else:
                        size = _human_bytes(getattr(a, "size", None))
                        attachment_bits.append(
                            f"<div class='attachment file'><a href='{a.url}'>{filename}</a><span class='size'>{size}</span></div>"
                        )
                attachments = "".join(attachment_bits)
                if not content and not attachments:
                    content = "<span class='empty'>[kein Inhalt]</span>"
                messages.append(
                    "<div class='msg'>"
                    f"<div class='avatar'>{f'<img src=\"{avatar}\" />' if avatar else ''}</div>"
                    "<div class='content'>"
                    "<div class='meta'>"
                    f"<span class='author' style='color:{role_color}'>"
                    f"{html_lib.escape(author_name)}</span>"
                    f"<span class='tag'>{html_lib.escape(author_tag)}</span>"
                    f"<span class='ts'>{ts}</span>"
                    "</div>"
                    f"<div class='body'>{content}</div>"
                    f"{attachments}"
                    "</div>"
                    "</div>"
                )
        except Exception:
            messages.append("<div class='msg'><div class='body'>[error] Transcript konnte nicht vollständig erstellt werden.</div></div>")

        html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>{html_lib.escape(title)}</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "gg sans","Noto Sans","Helvetica Neue",Arial,sans-serif; background:#313338; color:#dbdee1; padding:24px; }}
.header {{ margin-bottom:16px; padding:14px 18px; background:#2b2d31; border-radius:12px; border:1px solid #1f2023; }}
.header h1 {{ margin:0 0 6px 0; font-size:18px; font-weight:700; color:#ffffff; }}
.header .sub {{ color:#b5bac1; font-size:12px; }}
.msg {{ display:flex; gap:12px; padding:10px 8px; border-radius:10px; }}
.msg:hover {{ background:#2e3035; }}
.avatar img {{ width:40px; height:40px; border-radius:50%; }}
.content {{ flex:1; min-width:0; }}
.meta {{ font-size:12px; color:#b5bac1; display:flex; flex-wrap:wrap; gap:8px; align-items:baseline; }}
.author {{ font-weight:700; }}
.tag {{ color:#8e9297; }}
.ts {{ color:#8e9297; }}
.body {{ font-size:14px; line-height:1.4; word-break:break-word; }}
.empty {{ color:#8e9297; font-style:italic; }}
.attachment {{ margin-top:8px; }}
.attachment.image img {{ max-width:480px; border-radius:6px; border:1px solid #1f2023; }}
.attachment.file {{ background:#1e1f22; border:1px solid #111214; padding:8px 10px; border-radius:6px; display:inline-flex; gap:8px; align-items:center; }}
.attachment.file a {{ color:#00a8fc; text-decoration:none; }}
.attachment.file .size {{ color:#b5bac1; font-size:12px; }}
</style>
</head>
<body>
<div class="header">
  <h1>{html_lib.escape(thread.name or title)}</h1>
  <div class="sub">{html_lib.escape(header)}</div>
</div>
{''.join(messages)}
</body>
</html>
"""
        return html.encode("utf-8")

    async def _upload_transcript(self, guild_id: int, filename: str, data: bytes) -> str | None:
        url = str(self._g(guild_id, "ticket.transcript_upload_url", "") or "").strip()
        if not url:
            return None
        token = str(self._g(guild_id, "ticket.transcript_upload_token", "") or "").strip()
        mode = str(self._g(guild_id, "ticket.transcript_upload_mode", "multipart") or "multipart").strip()

        def _post_raw():
            req = urllib.request.Request(url, data=data, method="POST")
            req.add_header("Content-Type", "text/html; charset=utf-8")
            req.add_header("X-Filename", filename)
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read(), resp.getheader("Location")

        def _post_multipart():
            boundary = f"----StarryBoundary{uuid.uuid4().hex}"
            buf = io.BytesIO()
            buf.write(f"--{boundary}\r\n".encode("utf-8"))
            buf.write(
                f'Content-Disposition: form-data; name="files"; filename="{filename}"\r\n'.encode("utf-8")
            )
            buf.write(b"Content-Type: text/html; charset=utf-8\r\n\r\n")
            buf.write(data)
            buf.write(f"\r\n--{boundary}--\r\n".encode("utf-8"))
            body = buf.getvalue()

            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read(), resp.getheader("Location")

        try:
            if mode == "raw":
                body, location = await asyncio.to_thread(_post_raw)
            else:
                body, location = await asyncio.to_thread(_post_multipart)
            if location:
                return str(location)
            try:
                parsed = json.loads(body.decode("utf-8"))
                if isinstance(parsed, dict):
                    if parsed.get("url") or parsed.get("link"):
                        return str(parsed.get("url") or parsed.get("link") or "")
                    uploads = parsed.get("uploads") or []
                    if uploads and isinstance(uploads, list):
                        return str(uploads[0].get("url") or "")
                return None
            except Exception:
                return None
        except Exception:
            return None

    async def _send_transcript_dm(
        self,
        user: discord.User,
        thread: discord.Thread,
        t: dict,
    ) -> tuple[bool, str | None, str | None]:
        try:
            html_data = await self._render_html_transcript(thread, t)
            filename = f"ticket-{int(t['ticket_id'])}-transcript.html"
            guild_id = int(t.get("guild_id") or (thread.guild.id if thread and thread.guild else 0) or 0)
            upload_url = await self._upload_transcript(guild_id, filename, html_data)
            if upload_url:
                await user.send(f"Transcript: {upload_url}")
                return True, None, upload_url
            if len(html_data) <= 7_500_000:
                await user.send(file=discord.File(io.BytesIO(html_data), filename=filename))
                return True, None, None
            return False, "transcript_upload_failed", None
        except Exception as e:
            return False, f"{type(e).__name__}: {e}", None

    async def run_automation(self):
        await self.bot.wait_until_ready()
        now = datetime.now(timezone.utc)
        rows = await self.db.list_active_tickets(limit=500)
        for row in rows:
            t = {
                "ticket_id": int(row[0]),
                "guild_id": int(row[1]),
                "user_id": int(row[2]) if row[2] is not None else 0,
                "thread_id": int(row[3]),
                "status": str(row[4]),
                "claimed_by": int(row[5]) if row[5] is not None else None,
                "category_key": str(row[6]) if row[6] is not None else None,
                "created_at": row[7],
                "last_activity_at": row[8],
                "last_user_message_at": row[9],
                "last_staff_message_at": row[10],
                "first_staff_reply_at": row[11],
                "sla_breached_at": row[12],
                "priority": row[13],
                "status_label": row[14],
                "escalated_level": row[15],
            }
            guild_id = int(t["guild_id"])
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            auto_close_hours = float(self._g(guild_id, "ticket.auto_close_hours", 0) or 0)
            sla_minutes = float(self._g(guild_id, "ticket.sla_first_response_minutes", 0) or 0)

            thread = guild.get_thread(int(t["thread_id"]))
            if not thread:
                try:
                    fetched = await self.bot.fetch_channel(int(t["thread_id"]))
                    thread = fetched if isinstance(fetched, discord.Thread) else None
                except Exception:
                    thread = None

            if sla_minutes > 0 and not t.get("first_staff_reply_at") and not t.get("sla_breached_at"):
                created_at = _parse_iso(t.get("created_at"))
                if created_at and now - created_at >= timedelta(minutes=sla_minutes):
                    try:
                        view = build_thread_status_embed(
                            self.settings,
                            guild,
                            "⏱️ SLA überschritten",
                            "Noch keine Antwort vom Team.",
                            None,
                        )
                        if thread:
                            await thread.send(view=view)
                    except Exception:
                        pass
                    try:
                        await self.db.set_sla_breached(int(t["ticket_id"]), now.isoformat())
                    except Exception:
                        pass
                    await self._send_ticket_log(
                        guild,
                        "SLA überschritten",
                        "Noch keine Antwort vom Team.",
                        int(t["ticket_id"]),
                        thread=thread,
                        actor=None,
                    )

            if auto_close_hours > 0:
                last_activity = _parse_iso(t.get("last_activity_at")) or _parse_iso(t.get("created_at"))
                if last_activity and now - last_activity >= timedelta(hours=auto_close_hours):
                    try:
                        await self.db.close_ticket(int(t["ticket_id"]))
                    except Exception:
                        pass

                    try:
                        if thread:
                            view = build_thread_status_embed(
                                self.settings,
                                guild,
                                "🔒 Auto-Close",
                                "Ticket wurde wegen Inaktivität geschlossen.",
                                None,
                                banner_url=Banners.TICKETS_CLOSED,
                            )
                            await thread.send(view=view)
                            await thread.edit(archived=True, locked=True)
                    except Exception:
                        pass

                    await self._notify_user_update(
                        guild,
                        t,
                        "Ticket geschlossen",
                        "Dein Ticket wurde wegen Inaktivität automatisch geschlossen."
                    )
                    if thread and t.get("user_id"):
                        try:
                            user = await self.bot.fetch_user(int(t["user_id"]))
                            await self._send_transcript_dm(user, thread, t)
                        except Exception:
                            pass

                    await self._send_ticket_log(
                        guild,
                        "Auto-Close",
                        "Ticket wurde wegen Inaktivität geschlossen.",
                        int(t["ticket_id"]),
                        thread=thread,
                        actor=None,
                    )

                    await self.logger.emit(
                        self.bot,
                        "ticket_auto_closed",
                        {"ticket_id": int(t["ticket_id"])},
                    )

    async def submit_rating(self, interaction: discord.Interaction, ticket_id: int, rating: int, comment: str | None):
        row = await self.db.get_ticket(int(ticket_id))
        if not row:
            try:
                await interaction.response.send_message("Ticket nicht gefunden.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("Ticket nicht gefunden.", ephemeral=True)
            return

        if interaction.guild is not None:
            try:
                await interaction.response.send_message("Bitte nur in DMs bewerten.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("Bitte nur in DMs bewerten.", ephemeral=True)
            return

        ids_in_row = _extract_discord_ids(row)

        if ids_in_row and interaction.user.id not in ids_in_row:
            await self.logger.emit(self.bot, "ticket_rating_owner_mismatch", {
                "ticket_id": int(ticket_id),
                "interaction_user_id": int(interaction.user.id),
                "ids_in_db_row": ids_in_row[:10],
            })

        await self.db.set_rating(int(ticket_id), int(rating), comment)

        guild_id = int(row[1]) if row and len(row) > 1 else 0
        guild = self.bot.get_guild(guild_id) if guild_id else None

        try:
            await interaction.response.send_message(
                view=build_dm_rating_thanks_embed(self.settings, guild, int(rating)),
                ephemeral=False
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                view=build_dm_rating_thanks_embed(self.settings, guild, int(rating)),
                ephemeral=False
            )

        await self.logger.emit(self.bot, "ticket_rating", {
            "ticket_id": int(ticket_id),
            "user_id": int(interaction.user.id),
            "rating": int(rating),
            "comment": comment
        })

        try:
            t = _normalize_ticket_row(guild_id, row)
            if guild and t and t.get("thread_id"):
                thread = guild.get_thread(int(t["thread_id"]))
                if thread:
                    view = build_thread_rating_embed(self.settings, guild, int(interaction.user.id), int(rating),
                                                     comment)
                    await thread.send(view=view)
        except Exception:
            pass




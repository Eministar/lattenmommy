from __future__ import annotations

from datetime import datetime
import discord
from discord.utils import format_dt

from bot.utils.assets import Banners
from bot.utils.emojis import em


def _color(settings, guild: discord.Guild | None) -> int:
    gid = guild.id if guild else 0
    raw = str(settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
    try:
        return int(raw, 16)
    except Exception:
        return 0xB16B91


def _status_label(status: str) -> str:
    mapping = {
        "pending": "⏳ Pending",
        "reviewing": "🧪 Reviewing",
        "accepted": "✅ Accepted",
        "denied": "❌ Denied",
        "implemented": "🚀 Implemented",
    }
    return mapping.get(str(status or "pending").lower(), "⏳ Pending")


def _status_banner(status: str) -> str | None:
    key = str(status or "pending").lower()
    if key == "accepted":
        return Banners.SUGGESTION_ACCEPTED
    if key == "denied":
        return Banners.SUGGESTION_DENIED
    if key == "implemented":
        return Banners.SUGGESTION_IMPLEMENTED
    if key == "reviewing":
        return Banners.SUGGESTION_REVIEWING
    return Banners.SUGGESTION_PENDING


def _add_banner(container: discord.ui.Container, banner_url: str | None):
    if not banner_url:
        return
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=banner_url)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _add_avatar(container: discord.ui.Container, avatar_url: str | None):
    if not avatar_url:
        return
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=avatar_url)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def build_suggestion_summary_view(settings, guild: discord.Guild | None, data: dict, author: discord.abc.User | None):
    arrow2 = em(settings, "arrow2", guild) or "»"
    info = em(settings, "info", guild) or "ℹ️"
    uid = int(data.get("user_id") or 0)
    created_at = _parse_iso(data.get("created_at"))
    created_line = format_dt(created_at, style="f") if created_at else "unbekannt"
    upvotes = int(data.get("upvotes") or 0)
    downvotes = int(data.get("downvotes") or 0)
    score = int(upvotes - downvotes)
    title = str(data.get("title") or "").strip() or "Ohne Titel"
    content = str(data.get("content") or "").strip() or "—"
    status = str(data.get("status") or "pending").lower()
    admin_response = (data.get("admin_response") or "").strip()
    author_name = getattr(author, "display_name", None) or getattr(author, "name", None) or f"User {uid}"
    avatar_url = str(getattr(getattr(author, "display_avatar", None), "url", "") or "")

    response_block = admin_response if admin_response else "Noch keine Antwort."
    body = (
        f"{arrow2} Vorschlag wurde eingereicht.\n\n"
        f"┏`🧾` - ID: **#{int(data.get('id') or 0)}**\n"
        f"┣`👤` - User: <@{uid}> ({uid})\n"
        f"┣`📌` - Name: **{author_name}**\n"
        f"┣`🖼️` - Avatar: {avatar_url if avatar_url else '—'}\n"
        f"┣`📅` - Erstellt: {created_line}\n"
        f"┣`🏷️` - Status: **{_status_label(status)}**\n"
        f"┣`👍` - Upvotes: **{upvotes}**\n"
        f"┣`👎` - Downvotes: **{downvotes}**\n"
        f"┗`📊` - Score: **{score}**\n\n"
        f"**Titel**\n{title}\n\n"
        f"**Inhalt**\n{content}\n\n"
        f"**Admin Response**\n{response_block}"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, _status_banner(status))
    _add_avatar(container, avatar_url)
    container.add_item(discord.ui.TextDisplay(f"**{info} 𑁉 VORSCHLAG**\n{body}"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_suggestion_panel_container(settings, guild: discord.Guild | None, button: discord.ui.Button | None = None):
    arrow2 = em(settings, "arrow2", guild) or "»"
    sparkles = em(settings, "sparkles", guild) or "✨"
    lifebuoy = em(settings, "lifebuoy", guild) or "💡"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, Banners.SUGGESTION_PANEL)
    container.add_item(
        discord.ui.TextDisplay(
            f"**{lifebuoy} 𑁉 VORSCHLÄGE**\n"
            f"{arrow2} Reiche deine Idee ein und vote Vorschläge der Community.\n\n"
            f"{sparkles} **Ablauf**\n"
            "1) Button klicken\n"
            "2) Formular ausfüllen\n"
            "3) Thread wird erstellt\n"
            "4) Team prüft und setzt Status"
        )
    )
    if button:
        container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(button)
        container.add_item(row)
    return container

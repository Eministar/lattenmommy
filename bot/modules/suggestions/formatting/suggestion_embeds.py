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
        "pending": "Wartend",
        "reviewing": "In Prüfung",
        "accepted": "Angenommen",
        "denied": "Abgelehnt",
        "implemented": "Umgesetzt",
    }
    return mapping.get(str(status or "pending").lower(), "Wartend")


def _status_emoji(settings, guild: discord.Guild | None, status: str) -> str:
    key = str(status or "pending").lower()
    if key in {"accepted", "implemented"}:
        return em(settings, "green", guild) or "🟢"
    if key in {"denied"}:
        return em(settings, "red", guild) or "🔴"
    return em(settings, "orange", guild) or "🟠"


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


def _add_header_gallery(container: discord.ui.Container, banner_url: str | None, avatar_url: str | None):
    if not banner_url and not avatar_url:
        return
    try:
        gallery = discord.ui.MediaGallery()
        if banner_url:
            gallery.add_item(media=banner_url)
        if avatar_url:
            gallery.add_item(media=avatar_url)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _vote_stats(upvotes: int, downvotes: int) -> tuple[int, int, int]:
    total = max(0, int(upvotes) + int(downvotes))
    if total <= 0:
        return 0, 0, 0
    up_pct = round((int(upvotes) / total) * 100)
    down_pct = max(0, 100 - up_pct)
    return total, up_pct, down_pct


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
    total_votes, up_pct, down_pct = _vote_stats(upvotes, downvotes)
    title = str(data.get("title") or "").strip() or "Ohne Titel"
    content = str(data.get("content") or "").strip() or "—"
    status = str(data.get("status") or "pending").lower()
    status_emoji = _status_emoji(settings, guild, status)
    admin_response = (data.get("admin_response") or "").strip()
    author_name = getattr(author, "display_name", None) or getattr(author, "name", None) or f"User {uid}"
    up_icon = "📈"
    down_icon = "📉"
    vote_line = (
        f"┏`👍` - Zustimmung: **{upvotes}** ({up_pct}%)\n"
        f"┣`👎` - Ablehnung: **{downvotes}** ({down_pct}%)\n"
        f"┣`🧮` - Gesamt: **{total_votes}** Stimme(n)\n"
        f"┗`📊` - Score: **{score}** ({up_icon} {up_pct}% · {down_icon} {down_pct}%)"
    )

    response_block = admin_response if admin_response else "Noch keine Antwort."
    body = (
        f"{arrow2} Vorschlag wurde eingereicht und wird live aktualisiert.\n\n"
        f"┏`🧾` - ID: **#{int(data.get('id') or 0)}**\n"
        f"┣`👤` - User: <@{uid}> ({uid})\n"
        f"┣`📌` - Name: **{author_name}**\n"
        f"┣`📅` - Erstellt: {created_line}\n"
        f"┗`🏷️` - Status: {status_emoji} **{_status_label(status)}**\n\n"
        f"**Voting**\n{vote_line}\n\n"
        f"**Titel**\n{title}\n\n"
        f"**Inhalt**\n{content}\n\n"
        f"**Admin Response**\n{response_block}"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"**{info} 𑁉 VORSCHLAG**\n{body}"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_suggestion_panel_container(settings, guild: discord.Guild | None, button: discord.ui.Button | None = None):
    arrow2 = em(settings, "arrow2", guild) or "»"
    sparkles = em(settings, "sparkles", guild) or "✨"
    lifebuoy = em(settings, "lifebuoy", guild) or "💡"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_header_gallery(container, Banners.SUGGESTION_PANEL, None)
    container.add_item(
        discord.ui.TextDisplay(
            f"**{lifebuoy} 𑁉 VORSCHLÄGE**\n"
            f"{arrow2} Reiche deine Idee ein und vote Vorschläge der Community.\n\n"
            f"{sparkles} **Ablauf**\n"
            "┏`🧵` - Button klicken\n"
            "┣`📝` - Formular ausfüllen\n"
            "┣`📊` - Community stimmt live ab\n"
            "┗`🏷️` - Team setzt Status + Antwort"
        )
    )
    if button:
        container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        row.add_item(button)
        container.add_item(row)
    return container


def build_suggestion_thread_info_container(settings, guild: discord.Guild | None):
    info = em(settings, "info", guild) or "ℹ️"
    sparkles = em(settings, "sparkles", guild) or "✨"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_header_gallery(container, Banners.SUGGESTION_PANEL, None)
    container.add_item(
        discord.ui.TextDisplay(
            f"**{info} 𑁉 DISKUSSION**\n"
            "Hier kann der Vorschlag sachlich diskutiert werden.\n\n"
            f"{sparkles} Feedback mit Begründung hilft dem Team bei der Entscheidung."
        )
    )
    return container

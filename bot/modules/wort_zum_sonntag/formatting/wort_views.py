from __future__ import annotations

from datetime import datetime
import discord
from discord.utils import format_dt
from bot.utils.emojis import em
from bot.utils.assets import Banners


DEFAULT_COLOR = 0xB16B91


def parse_hex_color(value: str, default: int = DEFAULT_COLOR) -> int:
    if not value:
        return default
    v = str(value).strip().replace("#", "")
    try:
        return int(v, 16)
    except Exception:
        return default


def _color(settings, guild: discord.Guild | None) -> int:
    if guild:
        value = settings.get_guild(guild.id, "design.accent_color", "#B16B91")
    else:
        value = settings.get("design.accent_color", "#B16B91")
    return parse_hex_color(value)


def _clip(text: str, limit: int) -> str:
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    return t[: max(0, limit - 3)].rstrip() + "..."


def _fmt_dt(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value))
    except Exception:
        return str(value)
    if dt.tzinfo is None:
        return format_dt(dt)
    return format_dt(dt)


def _status_label(settings, guild: discord.Guild | None, status: str) -> tuple[str, str]:
    s = str(status or "pending").lower()
    if s == "accepted":
        return "✅ ANGENOMMEN", ""
    if s == "rejected":
        return "⛔ ABGELEHNT", ""
    if s == "posted":
        return "📣 GEPOSTET", ""
    return "⏳ ERWARTET", ""


def _add_banner(container: discord.ui.Container, banner_url: str):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=banner_url)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _banner_for_status(status: str) -> str:
    s = str(status or "pending").lower()
    if s in {"accepted", "posted"}:
        return Banners.WZM_ACCEPTED
    if s == "rejected":
        return Banners.WZM_DENIED
    return Banners.WZM_WAITING


def build_panel_container(settings, guild: discord.Guild | None, submit_button: discord.ui.Button):
    arrow2 = em(settings, "arrow2", guild) or "»"
    book = em(settings, "book", guild) or "📖"

    header = f"**{book} 𑁉 WORT ZUM SONNTAG**"
    intro = (
        f"{arrow2} Jede Woche wählen wir eine Weisheit aus der Community.\n"
        "Reiche deine eigene Weisheit ein und lass sie am Sonntag leuchten."
    )
    steps = (
        "**So läuft es**\n"
        "┏`📝` - Button klicken\n"
        "┣`💡` - Weisheit einreichen\n"
        "┣`🧑‍⚖️` - Team prüft\n"
        "┗`📅` - Sonntagspost wird gewählt"
    )
    rules = (
        "**Regeln für Einsendungen**\n"
        "┏`✅` - Kurz & verständlich (1–3 Sätze)\n"
        "┣`🚫` - Keine Beleidigungen, Hass oder NSFW\n"
        "┣`🚫` - Keine Werbung, Links oder Spam\n"
        "┗`🚫` - Keine privaten Daten"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{intro}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(steps))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(rules))
    row = discord.ui.ActionRow()
    row.add_item(submit_button)
    container.add_item(row)
    return container


def build_info_container(settings, guild: discord.Guild | None, ping_button: discord.ui.Button):
    arrow2 = em(settings, "arrow2", guild) or "»"
    info = em(settings, "info", guild) or "ℹ️"
    heart = em(settings, "hearts", guild) or "💜"

    title = f"**{info} 𑁉 WORT ZUM SONNTAG – INFO**"
    desc = (
        f"{arrow2} Dieses Forum sammelt Weisheiten aus der Community.\n\n"
        "┏`📅` - Jeden Sonntag wird eine Weisheit ausgewählt\n"
        "┣`📣` - Sie wird im Ziel-Channel gepostet\n"
        "┗`🧩` - Einreichung erfolgt über den Button im Panel"
    )
    rules = (
        "**Was ist erlaubt?**\n"
        "┏`✅` - Eigene, kurze Weisheiten\n"
        "┣`✅` - Respektvoll & allgemein verständlich\n"
        "┗`✅` - Keine Trigger/NSFW-Inhalte\n\n"
        "**Was ist nicht erlaubt?**\n"
        "┏`🚫` - Beleidigungen, Hate, Diskriminierung\n"
        "┣`🚫` - Werbung, Links, Spam\n"
        "┗`🚫` - Private Daten oder Doxxing\n\n"
        f"{heart} Danke fürs Teilen deiner Gedanken."
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, Banners.WZM_BANNER)
    container.add_item(discord.ui.TextDisplay(f"{title}\n{desc}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(rules))
    row = discord.ui.ActionRow()
    row.add_item(ping_button)
    container.add_item(row)
    return container


def build_submission_view(settings, guild: discord.Guild | None, data: dict) -> discord.ui.LayoutView:
    arrow2 = em(settings, "arrow2", guild) or "»"
    pen = em(settings, "pen", guild) or "📝"

    content = _clip(str(data.get("content", "")).strip(), 1200)
    status = str(data.get("status") or "pending")
    label, status_emoji = _status_label(settings, guild, status)
    status_text = f"{status_emoji} **{label}**".strip()

    created_at = _fmt_dt(data.get("created_at"))
    decided_at = _fmt_dt(data.get("decided_at"))
    posted_at = _fmt_dt(data.get("posted_at"))

    user_id = int(data.get("user_id") or 0)
    decided_by = int(data.get("decided_by") or 0)
    posted_channel_id = int(data.get("posted_channel_id") or 0)

    header = f"**{pen} 𑁉 WEISHEIT EINGEREICHT**"
    meta = (
        f"┏`👤` - Von: <@{user_id}>\n"
        f"┣`⏰` - Eingereicht: {created_at}\n"
        f"┗`📌` - Status: {status_text}"
    )
    quote = f"{arrow2} **Weisheit**\n>>> {content or '-'}"

    status_lines = []
    if status in {"accepted", "rejected"}:
        who = f"<@{decided_by}>" if decided_by else "—"
        status_lines.append(f"┏`🧑‍⚖️` - Geprüft von: {who}")
        status_lines.append(f"┗`🗓️` - Entscheidung: {decided_at}")
    elif status == "posted":
        channel_line = f"<#{posted_channel_id}>" if posted_channel_id else "—"
        status_lines.append(f"┏`📣` - Gepostet in: {channel_line}")
        status_lines.append(f"┗`🗓️` - Gepostet am: {posted_at}")
    else:
        status_lines.append("┗`🔎` - Prüfung: ausstehend")

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, _banner_for_status(status))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{meta}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(quote))
    view.add_item(container)

    status_container = discord.ui.Container(accent_colour=_color(settings, guild))
    status_container.add_item(discord.ui.TextDisplay("**STATUS**"))
    status_container.add_item(discord.ui.Separator())
    status_container.add_item(discord.ui.TextDisplay("\n".join(status_lines)))
    view.add_item(status_container)
    return view


def build_weekly_post_view(settings, guild: discord.Guild | None, data: dict) -> discord.ui.LayoutView:
    arrow2 = em(settings, "arrow2", guild) or "»"
    book = em(settings, "book", guild) or "📖"
    sparkles = em(settings, "sparkles", guild) or "✨"

    content = _clip(str(data.get("content", "")).strip(), 1000)
    user_id = int(data.get("user_id") or 0)

    header = f"**{book} 𑁉 WORT ZUM SONNTAG**"
    intro = f"{arrow2} Ausgewählte Weisheit der Woche"
    quote = f"{sparkles} >>> {content or '-'}"
    footer = f"Eingereicht von <@{user_id}>"

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{intro}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(quote))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(footer))
    view.add_item(container)
    return view

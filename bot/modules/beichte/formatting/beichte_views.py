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
        value = settings.get_guild(guild.id, "design.accent_color", "#C9965B")
    else:
        value = settings.get("design.accent_color", "#C9965B")
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


def _g(settings, guild: discord.Guild | None, key: str, default: str) -> str:
    try:
        if guild:
            value = settings.get_guild(guild.id, key, None)
        else:
            value = settings.get(key, None)
    except Exception:
        value = None
    return str(value) if value else default


def _default_info_text(settings, guild: discord.Guild | None) -> str:
    info = em(settings, "info", guild) or "ℹ️"
    heart = em(settings, "hearts", guild) or "💜"
    return (
        f"{info} **Was ist die Beichte?**\n"
        "Ein ruhiger Ort, um Dinge loszuwerden – ohne Druck, ohne Bewertung.\n\n"
        f"{heart} **Respekt‑Regel**\n"
        "Kein Hate, kein Leak von DMs, keine persönlichen Daten."
    )


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.BEICHTE)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def build_info_container(
    settings,
    guild: discord.Guild | None,
    anonymous_yes: discord.ui.Button,
    anonymous_no: discord.ui.Button,
):
    header = "**🕊️ 𑁉 BEICHTE – INFO**"
    info_text = _g(settings, guild, "beichte.info_text", _default_info_text(settings, guild))
    arrow2 = em(settings, "arrow2", guild) or "»"
    lock = em(settings, "lock", guild) or "🔒"
    sparkles = em(settings, "sparkles", guild) or "✨"
    rules = (
        "**So läuft’s ab**\n"
        "┏`🕵️` - Anonym wählen (Ja/Nein)\n"
        "┣`📝` - Beichte schreiben\n"
        "┗`🧵` - Thread wird erstellt\n\n"
        f"{arrow2} {lock} Anonym = dein Name erscheint nicht im Thread\n"
        f"{arrow2} {sparkles} Schreib ehrlich, aber respektvoll"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{info_text}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(rules))
    row = discord.ui.ActionRow()
    row.add_item(anonymous_yes)
    row.add_item(anonymous_no)
    container.add_item(row)
    return container


def build_submission_view(settings, guild: discord.Guild | None, data: dict) -> discord.ui.LayoutView:
    arrow2 = em(settings, "arrow2", guild) or "»"
    lock = em(settings, "lock", guild) or "🔒"
    heart = em(settings, "hearts", guild) or "💜"

    content = _clip(str(data.get("content", "")).strip(), 1400)
    user_id = int(data.get("user_id") or 0)
    anonymous = bool(data.get("anonymous"))
    created_at = _fmt_dt(data.get("created_at"))

    header = "**🕊️ 𑁉 BEICHTE – EINTRAG**"
    who = "Anonym" if anonymous else f"<@{user_id}>"
    meta = (
        f"┏`👤` - Von: {who}\n"
        f"┣`⏰` - Eingereicht: {created_at}\n"
        f"┗`{lock}` - Anonym: {'Ja' if anonymous else 'Nein'}"
    )
    body = f"{arrow2} **Beichte**\n>>> {content or '-'}"
    note = f"{heart} Respektvoll bleiben. Keine DMs oder privaten Infos teilen."

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{meta}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(body))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(note))
    view.add_item(container)
    return view


def build_thread_info_container(settings, guild: discord.Guild | None):
    info = em(settings, "info", guild) or "ℹ️"
    sparkles = em(settings, "sparkles", guild) or "✨"
    text = (
        f"{info} **Hinweis**\n"
        "Respektvoll bleiben, keine Angriffe, keine persönlichen Daten.\n\n"
        f"{sparkles} **Tipp**\n"
        "Wenn du anonym schreibst, wird dein Name nicht gezeigt."
    )
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(text))
    return container

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
    warn = em(settings, "orange", guild) or "🟠"
    heart = em(settings, "hearts", guild) or "💜"
    return (
        f"{info} **Was ist Seelsorge?**\n"
        "Hier kannst du offen über belastende Themen sprechen. "
        "Alles bleibt respektvoll, ohne Druck.\n\n"
        f"{warn} **Triggerwarnung**\n"
        "In diesem Bereich können sensible Inhalte vorkommen. "
        "Bitte achte auf dich und lies nur, wenn du dich stabil fühlst.\n\n"
        f"{heart} **Hinweis**\n"
        "Dies ist kein Ersatz für professionelle Hilfe."
    )


def _default_help_text(settings, guild: discord.Guild | None) -> str:
    arrow2 = em(settings, "arrow2", guild) or "»"
    return (
        "**Hilfe im Notfall**\n"
        f"{arrow2} **112** – Akute Gefahr / Rettungsdienst\n"
        f"{arrow2} **116 123** – TelefonSeelsorge (24/7)\n"
        f"{arrow2} **116 117** – Ärztlicher Bereitschaftsdienst\n"
        f"{arrow2} Online‑Chat: online.telefonseelsorge.de\n"
        f"{arrow2} Kinder/Jugendliche: **116 111** (Nummer gegen Kummer)"
    )


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.SEELSORGE)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def build_info_container(settings, guild: discord.Guild | None):
    header = f"**🧠 𑁉 SEELSORGE – INFO**"
    info_text = _g(settings, guild, "seelsorge.info_text", _default_info_text(settings, guild))
    help_text = _g(settings, guild, "seelsorge.help_text", _default_help_text(settings, guild))

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{info_text}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(help_text))
    return container


def build_panel_container(settings, guild: discord.Guild | None, submit_button: discord.ui.Button):
    arrow2 = em(settings, "arrow2", guild) or "»"
    sparkles = em(settings, "sparkles", guild) or "✨"

    header = "**🧩 𑁉 SEELSORGE – START**"
    steps = (
        "**So läuft es**\n"
        "┏`🧵` - Button klicken\n"
        "┣`📝` - Gedanken schreiben\n"
        "┣`🕵️` - Privat? (Anonym ja/nein)\n"
        "┗`💬` - Thread wird erstellt"
    )
    rules = (
        f"{arrow2} **Respektvoll, kein Druck, keine Bewertung.**\n"
        f"{sparkles} Privat = anonym: Nachrichten werden vom Bot neu gepostet."
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{steps}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(rules))
    row = discord.ui.ActionRow()
    row.add_item(submit_button)
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

    header = "**🧠 𑁉 SEELSORGE – EINTRAG**"
    who = "Anonym (Ersteller)" if anonymous else f"<@{user_id}> (Ersteller)"
    meta = (
        f"┏`👤` - Ersteller: {who}\n"
        f"┣`⏰` - Eingereicht: {created_at}\n"
        f"┗`{lock}` - Privat: {'Ja' if anonymous else 'Nein'}"
    )
    body = f"{arrow2} **Gedanken**\n>>> {content or '-'}"
    note = f"{heart} Sei respektvoll. Bei akuter Gefahr bitte 112."

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
    warn = em(settings, "orange", guild) or "🟠"
    info = em(settings, "info", guild) or "ℹ️"
    text = (
        f"{warn} **Triggerwarnung**\n"
        "In diesem Thread können sensible Inhalte vorkommen.\n\n"
        f"{info} **Sicherheits‑Hinweis**\n"
        "Akute Gefahr: **112** · TelefonSeelsorge: **116 123**"
    )
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(text))
    return container

from __future__ import annotations

from datetime import datetime
import discord
from discord.utils import format_dt
from bot.utils.assets import Banners
from bot.utils.emojis import em


def parse_hex_color(value: str | None, default: int = 0xB16B91) -> int:
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
    return parse_hex_color(value, 0xB16B91)


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.BOT_BANNER)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _wrap(container: discord.ui.Container) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def _format_duration(seconds: int | float | None) -> str:
    if not seconds:
        return "—"
    total = int(max(0, seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours or parts:
        parts.append(f"{hours}h")
    if minutes or parts:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def build_bot_status_view(
    settings,
    guild: discord.Guild,
    online: bool,
    now: datetime,
    started_at: datetime | None,
    guild_count: int,
    member_count: int,
    latency_ms: int,
) -> discord.ui.LayoutView:
    arrow2 = em(settings, "arrow2", guild) or "»"
    if online:
        status = em(settings, "green", guild) or "🟢"
        header = f"**{status} 𑁉 BOT ONLINE**"
        intro = f"{arrow2} Lattenmommy ist gestartet."
        time_line = f"┏`⏰` - Start: {format_dt(now, style='f')}\n"
    else:
        status = em(settings, "red", guild) or "🔴"
        header = f"**{status} 𑁉 BOT OFFLINE**"
        intro = f"{arrow2} Lattenmommy fährt runter."
        uptime = _format_duration((now - started_at).total_seconds()) if started_at else "—"
        time_line = f"┏`⏰` - Stop: {format_dt(now, style='f')}\n" f"┣`⌛` - Uptime: **{uptime}**\n"

    desc = (
        f"{intro}\n\n"
        f"{time_line}"
        f"┣`🏠` - Server: **{guild.name}**\n"
        f"┣`👥` - Members: **{member_count}**\n"
        f"┣`🧭` - Guilds: **{guild_count}**\n"
        f"┗`📡` - Ping: **{latency_ms}ms**"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    return _wrap(container)

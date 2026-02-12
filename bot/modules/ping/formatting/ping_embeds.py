from __future__ import annotations

import discord
from bot.utils.assets import Banners
from bot.utils.emojis import em


def _color(settings, guild: discord.Guild | None) -> int:
    gid = guild.id if guild else 0
    raw = str(settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
    try:
        return int(raw, 16)
    except Exception:
        return 0xB16B91


def build_ping_view(
    settings,
    guild: discord.Guild | None,
    ws_ms: int,
    api_ms: int,
    db_ms: int | None,
) -> discord.ui.LayoutView:
    ping_emoji = em(settings, "ping", guild) or "🏓"
    arrow2 = em(settings, "arrow2", guild) or "»"
    status = "Sehr gut" if ws_ms < 120 and api_ms < 450 else ("Stabil" if ws_ms < 220 and api_ms < 800 else "Langsam")
    db_text = f"{int(db_ms)} ms" if db_ms is not None else "n/a"

    header = f"**{ping_emoji} 𑁉 PING STATUS**"
    body = (
        f"{arrow2} Live-Status vom Bot.\n\n"
        f"┏`📡` - Gateway: **{int(ws_ms)} ms**\n"
        f"┣`⚡` - API: **{int(api_ms)} ms**\n"
        f"┣`🗄️` - DB: **{db_text}**\n"
        f"┗`✅` - Status: **{status}**"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.PING)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass
    container.add_item(discord.ui.TextDisplay(f"{header}\n{body}"))

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


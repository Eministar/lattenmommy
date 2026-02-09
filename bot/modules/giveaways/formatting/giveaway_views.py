from __future__ import annotations

import discord
from datetime import datetime
from discord.utils import format_dt
from bot.utils.emojis import em
from bot.utils.assets import Banners


DEFAULT_COLOR = 0xB16B91


def _color(settings, guild: discord.Guild | None) -> int:
    if guild:
        value = settings.get_guild(guild.id, "design.accent_color", "#B16B91")
    else:
        value = settings.get("design.accent_color", "#B16B91")
    v = str(value or "").replace("#", "").strip()
    try:
        return int(v, 16)
    except Exception:
        return DEFAULT_COLOR


def build_giveaway_container(
    settings,
    guild: discord.Guild | None,
    data: dict,
    join_button: discord.ui.Button,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    cheers = em(settings, "cheers", guild) or "🎉"
    info = em(settings, "info", guild) or "ℹ️"

    title = str(data.get("title") or "Giveaway").strip()
    sponsor = str(data.get("sponsor") or "—").strip()
    description = str(data.get("description") or "Gewinne dieses Giveaway!").strip()
    end_at = data.get("end_at")
    winners = int(data.get("winners") or 1)
    entries = int(data.get("entries") or 0)
    conditions = str(data.get("conditions") or "—")
    status = str(data.get("status") or "open")

    header = f"**{cheers} 𑁉 GIVEAWAY**"
    intro = f"{arrow2} **{description}**"
    details = [
        f"┏`🎁` - Preis: **{title}**",
        f"┣`🤝` - Sponsor: **{sponsor}**",
        f"┣`🏆` - Gewinner: **{winners}**",
    ]
    if isinstance(end_at, datetime):
        details.append(f"┣`⏰` - Ende: {format_dt(end_at, style='R')}")
    details.append(f"┗`📌` - Teilnehmer: **{entries}**")

    status_label = "OFFEN" if status == "open" else "GESCHLOSSEN"
    status_line = f"{info} Status: **{status_label}**"

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.GIVEAWAY)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass
    container.add_item(discord.ui.TextDisplay(f"{header}\n{intro}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("\n".join(details)))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**✅ Bedingungen**\n{conditions}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(status_line))
    row = discord.ui.ActionRow()
    row.add_item(join_button)
    container.add_item(row)
    return container

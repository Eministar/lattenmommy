from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import discord
from discord.utils import format_dt

from bot.utils.emojis import em


def parse_hex_color(value: str, default: int = 0xB16B91) -> int:
    if not value:
        return default
    v = str(value).strip().replace("#", "")
    try:
        return int(v, 16)
    except Exception:
        return default


def _color(settings, guild: discord.Guild | None):
    if guild:
        value = settings.get_guild(guild.id, "design.accent_color", "#B16B91")
    else:
        value = settings.get("design.accent_color", "#B16B91")
    return parse_hex_color(value)


def _footer(emb: discord.Embed, settings, guild: discord.Guild | None):
    if guild:
        ft = settings.get_guild(guild.id, "design.footer_text", None)
    else:
        ft = settings.get("design.footer_text", None)
    if ft:
        emb.set_footer(text=str(ft))


@dataclass(frozen=True)
class NewsItem:
    id: str
    title: str
    description: str
    url: str
    image_url: str | None
    published_at: datetime | None
    source: str = "Tagesschau"


def build_news_embed(settings, guild: discord.Guild | None, item: NewsItem) -> discord.Embed:
    arrow2 = em(settings, "arrow2", guild)
    info = em(settings, "info", guild) or "📰"
    lines = [f"┏`📰` - Quelle: **{item.source}**"]
    if item.published_at:
        lines.append(f"┣`🗓️` - {format_dt(item.published_at, style='f')}")
    lines.append(f"┗`🔗` - Mehr: [Artikel öffnen]({item.url})")
    desc = f"{arrow2} {item.description}\n\n" + "\n".join(lines)
    emb = discord.Embed(
        title=item.title,
        url=item.url or None,
        description=desc,
        color=_color(settings, guild),
    )
    emb.set_author(name=f"🌍 𑁉 WORLD NEWS")
    if item.image_url:
        emb.set_image(url=item.image_url)
    _footer(emb, settings, guild)
    return emb
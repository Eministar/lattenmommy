from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import discord
from discord.utils import format_dt

from bot.utils.emojis import em


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


def _footer(emb: discord.Embed, settings, guild: discord.Guild | None):
    if guild:
        ft = settings.get_guild(guild.id, "design.footer_text", None)
        bot_member = getattr(guild, "me", None)
    else:
        ft = settings.get("design.footer_text", None)
        bot_member = None
    if ft:
        if bot_member:
            emb.set_footer(text=bot_member.display_name, icon_url=bot_member.display_avatar.url)
        else:
            emb.set_footer(text=str(ft))


def _clip(text: str, limit: int) -> str:
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    return t[: max(0, limit - 3)].rstrip() + "..."


@dataclass(frozen=True)
class NewsItem:
    id: str
    title: str
    description: str
    url: str
    image_url: str | None
    published_at: datetime | None
    source: str = "Tagesschau"
    source_url: str | None = None
    video_id: str | None = None
    stats: dict | None = None
    channel: dict | None = None


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


def build_news_view(settings, guild: discord.Guild | None, item: NewsItem, ping_text: str | None = None) -> discord.ui.LayoutView:
    arrow2 = em(settings, "arrow2", guild) or "»"
    info = em(settings, "info", guild) or "📰"

    title = _clip(item.title, 150)
    desc = _clip(item.description, 700)

    header = f"**{info} 𑁉 NEWS-UPDATE**"
    meta = [f"┏`📰` - Quelle: **{item.source}**"]
    if item.published_at:
        meta.append(f"┣`🗓️` - {format_dt(item.published_at, style='f')}")
    meta.append("┗`🔗` - Mehr: Button unten")

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    if ping_text:
        container.add_item(discord.ui.TextDisplay(str(ping_text)))
        container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"{header}\n**{title}**"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"{arrow2} {desc}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("\n".join(meta)))

    if item.image_url:
        try:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=item.image_url)
            if item.channel:
                avatar = str(item.channel.get("avatar_url") or "").strip()
                if avatar:
                    gallery.add_item(media=avatar, description="Channel")
            container.add_item(discord.ui.Separator())
            container.add_item(gallery)
        except Exception:
            pass

    if item.video_id and item.stats:
        views = _fmt_number(item.stats.get("views"))
        likes = _fmt_number(item.stats.get("likes"))
        stats_text = f"┏`👀` - Aufrufe: **{views}**\n┗`👍` - Likes: **{likes}**"
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"**📊 YouTube Stats**\n{stats_text}"))

    if item.channel:
        name = str(item.channel.get("name") or "").strip()
        link = str(item.channel.get("url") or "").strip()
        subs = _fmt_number(item.channel.get("subscribers"))
        footer = f"Kanal: **{name or '—'}**"
        if link:
            footer = f"Kanal: [{name or 'Link'}]({link})"
        footer += f" • Abos: **{subs}**"
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(footer))

    if item.url:
        row = discord.ui.ActionRow()
        row.add_item(
            discord.ui.Button(
                label="Artikel öffnen" if not item.video_id else "Video öffnen",
                style=discord.ButtonStyle.link,
                url=item.url,
                emoji="🔗",
            )
        )
        container.add_item(row)

    view.add_item(container)
    return view


def _fmt_number(value: int | str | None) -> str:
    try:
        n = int(value or 0)
    except Exception:
        return "0"
    return f"{n:,}".replace(",", ".")

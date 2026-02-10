from __future__ import annotations

import discord
from bot.utils.emojis import em
from bot.utils.assets import Banners


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


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.COUNTING)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _build_view(settings, guild: discord.Guild | None, header: str, body: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{body}"))
    view.add_item(container)
    return view


def build_counting_fail_embed(
    settings,
    guild: discord.Guild | None,
    reason: str,
    expected: int | None,
    got: int | None,
    highscore: int,
    total_fails: int,
    reset_to: int = 1,
) -> discord.Embed:
    red = em(settings, "red", guild) or "🔴"
    arrow2 = em(settings, "arrow2", guild) or "»"

    exp = f"**{expected}**" if expected is not None else "—"
    got_val = f"**{got}**" if got is not None else "—"
    desc = (
        f"{arrow2} {reason}\n\n"
        f"┏`🎯` - Erwartet: {exp}\n"
        f"┣`📨` - Gesendet: {got_val}\n"
        f"┣`🏆` - Highscore: **{highscore}**\n"
        f"┣`🔁` - Reset: **{reset_to}**\n"
        f"┗`💥` - Reset-Count: **{total_fails}**"
    )

    header = f"**{red} 𑁉 COUNTING FAIL**"
    return _build_view(settings, guild, header, desc)


def build_counting_milestone_embed(
    settings,
    guild: discord.Guild | None,
    milestone: int,
    highscore: int,
    total_counts: int,
    total_fails: int,
) -> discord.Embed:
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"

    desc = (
        f"{arrow2} Meilenstein erreicht.\n\n"
        f"┏`🔢` - Count: **{milestone}**\n"
        f"┣`🏆` - Highscore: **{highscore}**\n"
        f"┣`📊` - Gesamt gezählt: **{total_counts}**\n"
        f"┗`⚠️` - Gesamt Fails: **{total_fails}**"
    )

    header = f"**{info} 𑁉 MEILENSTEIN**"
    return _build_view(settings, guild, header, desc)


def build_counting_record_embed(
    settings,
    guild: discord.Guild | None,
    count: int,
    highscore: int,
) -> discord.Embed:
    green = em(settings, "green", guild) or "🟢"
    arrow2 = em(settings, "arrow2", guild) or "»"

    desc = (
        f"{arrow2} Neuer Rekord erreicht.\n\n"
        f"┏`🔢` - Count: **{count}**\n"
        f"┗`🏆` - Highscore: **{highscore}**"
    )

    header = f"**{green} 𑁉 NEUER REKORD**"
    return _build_view(settings, guild, header, desc)

from __future__ import annotations

import discord
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


def build_counting_fail_embed(
    settings,
    guild: discord.Guild | None,
    reason: str,
    expected: int | None,
    got: int | None,
    highscore: int,
    reset_to: int = 1,
) -> discord.Embed:
    red = em(settings, "red", guild) or "??"
    arrow2 = em(settings, "arrow2", guild) or "?"

    exp = f"**{expected}**" if expected is not None else "?"
    got_val = f"**{got}**" if got is not None else "?"
    desc = (
        f"{arrow2} {reason}\n\n"
        f"?`??` - Erwartet: {exp}\n"
        f"?`??` - Gesendet: {got_val}\n"
        f"?`??` - Highscore: **{highscore}**\n"
        f"?`??` - Reset: **{reset_to}**"
    )

    emb = discord.Embed(
        title=f"{red} ?? COUNTING FAIL",
        description=desc,
        color=_color(settings, guild),
    )
    _footer(emb, settings, guild)
    return emb


def build_counting_milestone_embed(
    settings,
    guild: discord.Guild | None,
    milestone: int,
    highscore: int,
    total_counts: int,
    total_fails: int,
) -> discord.Embed:
    info = em(settings, "info", guild) or "??"
    arrow2 = em(settings, "arrow2", guild) or "?"

    desc = (
        f"{arrow2} Meilenstein erreicht.\n\n"
        f"?`??` - Count: **{milestone}**\n"
        f"?`??` - Highscore: **{highscore}**\n"
        f"?`?` - Gesamt gez?hlt: **{total_counts}**\n"
        f"?`?` - Gesamt Fails: **{total_fails}**"
    )

    emb = discord.Embed(
        title=f"{info} ?? MEILENSTEIN",
        description=desc,
        color=_color(settings, guild),
    )
    _footer(emb, settings, guild)
    return emb


def build_counting_record_embed(
    settings,
    guild: discord.Guild | None,
    count: int,
    highscore: int,
) -> discord.Embed:
    green = em(settings, "green", guild) or "??"
    arrow2 = em(settings, "arrow2", guild) or "?"

    desc = (
        f"{arrow2} Neuer Rekord erreicht.\n\n"
        f"?`??` - Count: **{count}**\n"
        f"?`??` - Highscore: **{highscore}**"
    )

    emb = discord.Embed(
        title=f"{green} ?? NEUER REKORD",
        description=desc,
        color=_color(settings, guild),
    )
    _footer(emb, settings, guild)
    return emb

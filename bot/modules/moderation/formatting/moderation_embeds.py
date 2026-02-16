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


def _cut(s: str | None, n: int) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def build_timeout_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    target: discord.Member,
    minutes: int,
    strikes: int,
    reason: str | None,
    case_id: int | None = None,
):
    orange = em(settings, "orange", guild) or "🟠"
    arrow2 = em(settings, "arrow2", guild) or "»"

    desc = (
        f"{arrow2} Timeout wurde angewendet.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`⏳` - Dauer: **{int(minutes)} Minuten**\n"
        f"┣`📌` - Strikes: **{int(strikes)}**\n"
        f"┣`🆔` - Case: `{case_id if case_id else '—'}`\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )

    emb = discord.Embed(title=f"{orange} 𑁉 TIMEOUT", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_warn_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    target: discord.Member,
    strikes: int,
    reason: str | None,
    case_id: int | None = None,
):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"

    desc = (
        f"{arrow2} Warnung wurde vergeben.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`📌` - Strikes: **{int(strikes)}**\n"
        f"┣`🆔` - Case: `{case_id if case_id else '—'}`\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )

    emb = discord.Embed(title=f"{info} 𑁉 WARNUNG", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_kick_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    target: discord.Member,
    reason: str | None,
    case_id: int | None = None,
):
    red = em(settings, "red", guild) or "🟥"
    arrow2 = em(settings, "arrow2", guild) or "»"

    desc = (
        f"{arrow2} User wurde gekickt.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`🆔` - Case: `{case_id if case_id else '—'}`\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )

    emb = discord.Embed(title=f"{red} 𑁉 KICK", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_ban_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    target: discord.User | discord.Member,
    delete_days: int,
    reason: str | None,
    case_id: int | None = None,
):
    red = em(settings, "red", guild) or "🟥"
    arrow2 = em(settings, "arrow2", guild) or "»"

    uid = int(getattr(target, "id", 0))
    mention = f"<@{uid}>" if uid else "—"

    desc = (
        f"{arrow2} User wurde gebannt.\n\n"
        f"┏`👤` - User: {mention} ({uid})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`🧹` - Delete Days: **{int(delete_days)}**\n"
        f"┣`🆔` - Case: `{case_id if case_id else '—'}`\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )

    emb = discord.Embed(title=f"{red} 𑁉 BAN", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_purge_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    channel: discord.TextChannel,
    deleted: int,
    requested: int,
    user: discord.Member | None,
    case_id: int | None = None,
):
    broom = em(settings, "money", guild) or "🧹"
    arrow2 = em(settings, "arrow2", guild) or "»"
    who = user.mention if user else "Alle"

    desc = (
        f"{arrow2} Nachrichten wurden gelöscht.\n\n"
        f"┏`📍` - Kanal: {channel.mention} ({channel.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`👤` - Filter: {who}\n"
        f"┣`📦` - Requested: **{int(requested)}**\n"
        f"┣`🆔` - Case: `{case_id if case_id else '—'}`\n"
        f"┗`✅` - Deleted: **{int(deleted)}**"
    )

    emb = discord.Embed(title=f"{broom} 𑁉 PURGE", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_unwarn_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    target: discord.Member,
    removed: int,
):
    green = em(settings, "green", guild) or "🟢"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} Warn-Einträge wurden entfernt.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┗`🧹` - Entfernt: **{int(removed)}**"
    )
    emb = discord.Embed(title=f"{green} 𑁉 UNWARN", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_case_reason_updated_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    case_id: int,
    user_id: int,
    reason: str | None,
):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} Case-Grund wurde aktualisiert.\n\n"
        f"┏`🆔` - Case: `{int(case_id)}`\n"
        f"┣`👤` - User: <@{int(user_id)}>\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┗`📝` - Neuer Grund: {_cut(reason, 900) if reason else '—'}"
    )
    emb = discord.Embed(title=f"{info} 𑁉 CASE UPDATE", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_channel_access_embed(
    settings,
    guild: discord.Guild,
    moderator: discord.Member,
    channel: discord.TextChannel,
    mode: str,
    locked: bool,
):
    icon = "🔒" if locked else "🔓"
    title = "CHANNEL LOCK" if locked else "CHANNEL UNLOCK"
    mode_label = {"send": "Schreiben", "view": "Sehen", "all": "Schreiben + Sehen"}.get(str(mode), "Schreiben + Sehen")
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} Channel-Rechte wurden aktualisiert.\n\n"
        f"┏`📍` - Kanal: {channel.mention} ({channel.id})\n"
        f"┣`🧩` - Modus: **{mode_label}**\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┗`⚙️` - Status: **{'Gesperrt' if locked else 'Entsperrt'}**"
    )
    emb = discord.Embed(title=f"{icon} 𑁉 {title}", description=desc, color=_color(settings, guild))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings, guild)
    return emb

from __future__ import annotations

import traceback
import discord
from discord.utils import format_dt
from datetime import datetime
from bot.utils.emojis import em


def parse_hex_color(value: str | None, default: int = 0xB16B91) -> int:
    if not value:
        return default
    v = str(value).strip().replace("#", "")
    try:
        return int(v, 16)
    except Exception:
        return default


def _color(settings) -> int:
    return parse_hex_color(settings.get("design.accent_color", "#B16B91"), 0xB16B91)


def _footer(emb: discord.Embed, settings):
    ft = settings.get("design.footer_text", None)
    if ft:
        emb.set_footer(text=str(ft))


def _cut(s: str | None, n: int) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= n else s[: n - 3] + "..."


def _actor_line(actor: discord.Member | None) -> str:
    if not actor:
        return "—"
    return f"{actor.mention} ({actor.id})"


def build_timeout_embed(settings, guild: discord.Guild, moderator: discord.Member, target: discord.Member, minutes: int, strikes: int, reason: str | None):
    orange = em(settings, "orange", guild) or "🟠"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} Timeout wurde angewendet.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`⏳` - Dauer: **{minutes} Minuten**\n"
        f"┣`📌` - Strikes: **{strikes}**\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )
    emb = discord.Embed(title=f"{orange} 𑁉 TIMEOUT", description=desc, color=_color(settings))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings)
    return emb


def build_warn_embed(settings, guild: discord.Guild, moderator: discord.Member, target: discord.Member, strikes: int, reason: str | None):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} Warnung wurde vergeben.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`📌` - Strikes: **{strikes}**\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )
    emb = discord.Embed(title=f"{info} 𑁉 WARNUNG", description=desc, color=_color(settings))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings)
    return emb


def build_kick_embed(settings, guild: discord.Guild, moderator: discord.Member, target: discord.Member, reason: str | None):
    red = em(settings, "red", guild) or "🟥"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} User wurde gekickt.\n\n"
        f"┏`👤` - User: {target.mention} ({target.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )
    emb = discord.Embed(title=f"{red} 𑁉 KICK", description=desc, color=_color(settings))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings)
    return emb


def build_ban_embed(settings, guild: discord.Guild, moderator: discord.Member, target: discord.User | discord.Member, delete_days: int, reason: str | None):
    red = em(settings, "red", guild) or "🟥"
    arrow2 = em(settings, "arrow2", guild) or "»"
    uid = int(getattr(target, "id", 0))
    mention = f"<@{uid}>" if uid else "—"
    desc = (
        f"{arrow2} User wurde gebannt.\n\n"
        f"┏`👤` - User: {mention} ({uid})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`🧹` - Delete Days: **{int(delete_days)}**\n"
        f"┗`📝` - Grund: {_cut(reason, 900) if reason else '—'}"
    )
    emb = discord.Embed(title=f"{red} 𑁉 BAN", description=desc, color=_color(settings))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings)
    return emb


def build_purge_embed(settings, guild: discord.Guild, moderator: discord.Member, channel: discord.TextChannel, deleted: int, requested: int, user: discord.Member | None):
    money = em(settings, "money", guild) or "🧹"
    arrow2 = em(settings, "arrow2", guild) or "»"
    who = user.mention if user else "Alle"
    desc = (
        f"{arrow2} Nachrichten wurden gelöscht.\n\n"
        f"┏`📍` - Kanal: {channel.mention} ({channel.id})\n"
        f"┣`🧑‍⚖️` - Moderator: {moderator.mention}\n"
        f"┣`👤` - Filter: {who}\n"
        f"┣`📦` - Requested: **{int(requested)}**\n"
        f"┗`✅` - Deleted: **{int(deleted)}**"
    )
    emb = discord.Embed(title=f"{money} 𑁉 PURGE", description=desc, color=_color(settings))
    emb.set_author(name=moderator.display_name, icon_url=moderator.display_avatar.url)
    _footer(emb, settings)
    return emb


def build_message_edited_embed(settings, guild: discord.Guild, author: discord.Member | None, channel: discord.abc.GuildChannel, before: str, after: str, msg_id: int):
    chat = em(settings, "chat", guild) or "💬"
    desc = (
        f"┏`👤` - User: {author.mention if author else 'Unbekannt'} ({author.id if author else '—'})\n"
        f"┣`📍` - Nachricht: {channel.mention}\n"
        f"┗`🆔` - ID: `{msg_id}`\n\n"
        f"🔴 **Vorher:**\n{_cut(before, 1500) or '—'}\n\n"
        f"🟢 **Nachher:**\n{_cut(after, 1500) or '—'}"
    )
    emb = discord.Embed(title=f"{chat} 𑁉 NACHRICHT BEARBEITET!", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_message_deleted_embed(settings, guild: discord.Guild, author: discord.Member | None, channel: discord.abc.GuildChannel, content: str, msg_id: int):
    red = em(settings, "red", guild) or "🟥"
    desc = (
        f"┏`👤` - User: {author.mention if author else 'Unbekannt'} ({author.id if author else '—'})\n"
        f"┣`📍` - Kanal: {channel.mention}\n"
        f"┗`🆔` - ID: `{msg_id}`\n\n"
        f"┏`📝` - Nachricht-Inhalt:\n{_cut(content, 1800) or '—'}"
    )
    emb = discord.Embed(title=f"{red} 𑁉 NACHRICHT GELÖSCHT!", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_join_embed(settings, guild: discord.Guild, member: discord.Member):
    green = em(settings, "green", guild) or "🟩"
    desc = (
        f"┏`👤` - User: {member.mention} ({member.id})\n"
        f"┗`🌈` - Account erstellt: {format_dt(member.created_at, style='R')}"
    )
    emb = discord.Embed(title=f"{green} 𑁉 JOIN", description=desc, color=_color(settings))
    emb.set_thumbnail(url=member.display_avatar.url)
    _footer(emb, settings)
    return emb


def build_leave_embed(settings, guild: discord.Guild, user: discord.User):
    red = em(settings, "red", guild) or "🟥"
    desc = f"┏`👤` - User: <@{user.id}> ({user.id})\n┗`🌈` - Account erstellt: {format_dt(user.created_at, style='R')}"
    emb = discord.Embed(title=f"{red} 𑁉 LEAVE", description=desc, color=_color(settings))
    emb.set_thumbnail(url=user.display_avatar.url)
    _footer(emb, settings)
    return emb


def _channel_kind(ch: discord.abc.GuildChannel) -> str:
    try:
        t = getattr(ch, "type", None)
        return str(t)
    except Exception:
        return "unknown"


def build_channel_created_embed(settings, guild: discord.Guild, channel: discord.abc.GuildChannel, actor: discord.Member | None):
    green = em(settings, "green", guild) or "🟩"
    desc = (
        f"┏`📍` - Kanal: {getattr(channel, 'mention', '#?')} ({channel.id})\n"
        f"┣`🧩` - Typ: {_channel_kind(channel)}\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}"
    )
    emb = discord.Embed(title=f"{green} 𑁉 KANAL ERSTELLT", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_channel_deleted_embed(settings, guild: discord.Guild, channel: discord.abc.GuildChannel, actor: discord.Member | None):
    red = em(settings, "red", guild) or "🟥"
    name = getattr(channel, "name", "unknown")
    desc = (
        f"┏`📍` - Kanal: **{name}** ({channel.id})\n"
        f"┣`🧩` - Typ: {_channel_kind(channel)}\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}"
    )
    emb = discord.Embed(title=f"{red} 𑁉 KANAL GELÖSCHT", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_channel_updated_embed(settings, guild: discord.Guild, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel, actor: discord.Member | None):
    changes: list[str] = []

    try:
        if getattr(before, "name", None) != getattr(after, "name", None):
            changes.append(f"┏`📝` - Name:\n`{getattr(before,'name','—')}` → `{getattr(after,'name','—')}`")
    except Exception:
        pass

    try:
        if hasattr(before, "topic") and hasattr(after, "topic"):
            if getattr(before, "topic", None) != getattr(after, "topic", None):
                changes.append(f"┏`📌` - Topic:\n`{_cut(getattr(before,'topic',None),200) or '—'}` → `{_cut(getattr(after,'topic',None),200) or '—'}`")
    except Exception:
        pass

    try:
        if hasattr(before, "slowmode_delay") and hasattr(after, "slowmode_delay"):
            if int(getattr(before, "slowmode_delay", 0)) != int(getattr(after, "slowmode_delay", 0)):
                changes.append(f"┏`🐌` - Slowmode: `{int(getattr(before,'slowmode_delay',0))}` → `{int(getattr(after,'slowmode_delay',0))}`")
    except Exception:
        pass

    try:
        if hasattr(before, "nsfw") and hasattr(after, "nsfw"):
            if bool(getattr(before, "nsfw", False)) != bool(getattr(after, "nsfw", False)):
                changes.append(f"┏`🔞` - NSFW: `{bool(getattr(before,'nsfw',False))}` → `{bool(getattr(after,'nsfw',False))}`")
    except Exception:
        pass

    if not changes:
        return None

    info = em(settings, "info", guild) or "ℹ️"
    head = (
        f"┏`📍` - Kanal: {getattr(after,'mention','#?')} ({after.id})\n"
        f"┣`🧩` - Typ: {_channel_kind(after)}\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}\n\n"
    )
    body = "\n\n".join(changes)
    emb = discord.Embed(title=f"{info} 𑁉 KANAL UPDATED", description=head + body, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_role_created_embed(settings, guild: discord.Guild, role: discord.Role, actor: discord.Member | None):
    green = em(settings, "green", guild) or "🟩"
    desc = (
        f"┏`🏷️` - Rolle: {role.mention} ({role.id})\n"
        f"┣`🎨` - Farbe: `{role.color}`\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}"
    )
    emb = discord.Embed(title=f"{green} 𑁉 ROLLE ERSTELLT", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_role_deleted_embed(settings, guild: discord.Guild, role: discord.Role, actor: discord.Member | None):
    red = em(settings, "red", guild) or "🟥"
    desc = (
        f"┏`🏷️` - Rolle: **{role.name}** ({role.id})\n"
        f"┣`🎨` - Farbe: `{role.color}`\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}"
    )
    emb = discord.Embed(title=f"{red} 𑁉 ROLLE GELÖSCHT", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_role_updated_embed(settings, guild: discord.Guild, before: discord.Role, after: discord.Role, actor: discord.Member | None):
    changes: list[str] = []

    if before.name != after.name:
        changes.append(f"┏`📝` - Name:\n`{before.name}` → `{after.name}`")

    if before.color != after.color:
        changes.append(f"┏`🎨` - Farbe:\n`{before.color}` → `{after.color}`")

    if before.hoist != after.hoist:
        changes.append(f"┏`📌` - Hoist:\n`{before.hoist}` → `{after.hoist}`")

    if before.mentionable != after.mentionable:
        changes.append(f"┏`🔔` - Mentionable:\n`{before.mentionable}` → `{after.mentionable}`")

    try:
        if before.permissions.value != after.permissions.value:
            changes.append("┏`🔑` - Permissions: geändert")
    except Exception:
        pass

    if not changes:
        return None

    info = em(settings, "info", guild) or "ℹ️"
    head = (
        f"┏`🏷️` - Rolle: {after.mention} ({after.id})\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}\n\n"
    )
    body = "\n\n".join(changes)
    emb = discord.Embed(title=f"{info} 𑁉 ROLLE UPDATED", description=head + body, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_member_roles_changed_embed(settings, guild: discord.Guild, before: discord.Member, after: discord.Member, actor: discord.Member | None):
    b = {r.id for r in before.roles}
    a = {r.id for r in after.roles}
    added = [r for r in after.roles if r.id in (a - b) and r.name != "@everyone"]
    removed = [r for r in before.roles if r.id in (b - a) and r.name != "@everyone"]

    if not added and not removed:
        return None

    info = em(settings, "info", guild) or "ℹ️"
    add_s = ", ".join([r.mention for r in added]) if added else "—"
    rem_s = ", ".join([r.mention for r in removed]) if removed else "—"

    desc = (
        f"┏`👤` - User: {after.mention} ({after.id})\n"
        f"┣`➕` - Added: {add_s}\n"
        f"┣`➖` - Removed: {rem_s}\n"
        f"┗`🧑` - Actor: {_actor_line(actor)}"
    )
    emb = discord.Embed(title=f"{info} 𑁉 USER-ROLLEN UPDATED", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb


def build_bot_error_embed(settings, guild: discord.Guild | None, where: str, err: BaseException, extra: dict | None = None):
    red = em(settings, "red", guild) or "🟥"
    info = em(settings, "info", guild) or "ℹ️"

    tb = "".join(traceback.format_exception(type(err), err, err.__traceback__))
    tb = _cut(tb, 1800)

    lines = []
    if extra:
        for k, v in extra.items():
            lines.append(f"┣`{k}`: {v}")
        if lines:
            lines[0] = lines[0].replace("┣", "┏", 1)
            lines[-1] = lines[-1].replace("┣", "┗", 1)

    desc = (
        f"┏`📍` - Where: `{_cut(where, 120)}`\n"
        f"┣`💥` - Type: `{type(err).__name__}`\n"
        f"┗`🧾` - Message: `{_cut(str(err), 400)}`\n\n"
        + ("\n".join(lines) + "\n\n" if lines else "")
        + f"```py\n{tb}\n```"
    )

    emb = discord.Embed(title=f"{red} 𑁉 BOT FEHLER", description=desc, color=_color(settings))
    _footer(emb, settings)
    return emb

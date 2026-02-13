from __future__ import annotations

import discord

from bot.utils.assets import Banners
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


def _add_banner(container: discord.ui.Container, banner_url: str | None):
    if not banner_url:
        return
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=banner_url)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _to_role_ids(raw) -> list[int]:
    if isinstance(raw, (tuple, set)):
        raw = list(raw)
    elif isinstance(raw, str):
        raw = [p.strip() for p in raw.split(",") if p.strip()]
    elif not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            if isinstance(item, dict):
                out.append(int(item.get("role_id", 0) or 0))
            else:
                out.append(int(item))
        except Exception:
            continue
    return [int(v) for v in out if int(v) > 0]


def _non_bot_count(role: discord.Role) -> int:
    return sum(1 for m in role.members if not getattr(m, "bot", False))


def _raw_from_base(settings, dotted: str):
    node = getattr(settings, "_base", {}) or {}
    for part in str(dotted).split("."):
        if not isinstance(node, dict) or part not in node:
            return []
        node = node[part]
    return node


def _role_ids_with_fallback(settings, guild: discord.Guild, keys: list[str]) -> list[int]:
    for key in keys:
        raw = settings.get_guild(guild.id, key, None)
        if raw not in (None, "", [], {}):
            ids = _to_role_ids(raw)
            if ids:
                return ids
        raw = settings.get(key, [])
        if raw not in (None, "", [], {}):
            ids = _to_role_ids(raw)
            if ids:
                return ids
        raw = _raw_from_base(settings, key)
        if raw not in (None, "", [], {}):
            ids = _to_role_ids(raw)
            if ids:
                return ids
    return []


def _non_bot_members(role: discord.Role) -> list[discord.Member]:
    return [m for m in role.members if not getattr(m, "bot", False)]


def _chunk(seq: list[str], size: int) -> list[list[str]]:
    return [seq[i:i + size] for i in range(0, len(seq), size)]


def _boxed(lines: list[str], empty: str) -> str:
    if not lines:
        return f"┗{empty}"
    out: list[str] = []
    for i, line in enumerate(lines):
        if len(lines) == 1:
            prefix = "┗"
        elif i == 0:
            prefix = "┏"
        elif i == len(lines) - 1:
            prefix = "┗"
        else:
            prefix = "┣"
        out.append(f"{prefix}{line}")
    return "\n".join(out)


def _roles_for_category(settings, guild: discord.Guild, category: str) -> tuple[str, str, str | None, list[discord.Role]]:
    cat = str(category or "").lower()
    if cat == "achievements":
        items = settings.get_guild(guild.id, "achievements.items", []) or []
        role_ids: list[int] = []
        for item in items:
            try:
                rid = int((item or {}).get("role_id", 0) or 0)
            except Exception:
                rid = 0
            if rid > 0:
                role_ids.append(rid)
        roles = [r for rid in role_ids if (r := guild.get_role(int(rid)))]
        return (
            "Erfolgsrollen",
            "🏆 𑁉 ROLLEN-INFO – ERFOLGE",
            Banners.ROLES_ACHIEVEMENTS,
            roles,
        )

    if cat == "level":
        raw = settings.get_guild(guild.id, "user_stats.level_roles", {}) or {}
        pairs: list[tuple[int, int]] = []
        for level, rid in raw.items():
            try:
                pairs.append((int(level), int(rid)))
            except Exception:
                continue
        pairs.sort(key=lambda x: x[0])
        roles = [r for _, rid in pairs if rid > 0 and (r := guild.get_role(int(rid)))]
        return (
            "Levelrollen",
            "⭐ 𑁉 ROLLEN-INFO – LEVEL",
            Banners.ROLES_LEVEL,
            roles,
        )

    if cat == "team":
        role_ids = _role_ids_with_fallback(settings, guild, ["role-info.team_role_ids", "roles.team_role_ids"])
        roles = [r for rid in role_ids if (r := guild.get_role(int(rid)))]
        return (
            "Teamrollen",
            "🛡️ 𑁉 ROLLEN-INFO – TEAM",
            Banners.ROLES_TEAM,
            roles,
        )

    role_ids = _role_ids_with_fallback(settings, guild, ["role-info.special_role_ids", "roles.special_role_ids"])
    roles = [r for rid in role_ids if (r := guild.get_role(int(rid)))]
    return (
        "Sonderrollen",
        "✨ 𑁉 ROLLEN-INFO – SONDER",
        Banners.ROLES_OTHER,
        roles,
    )


def build_roles_info_panel_container(settings, guild: discord.Guild, select: discord.ui.Select):
    arrow2 = em(settings, "arrow2", guild) or "»"
    info = em(settings, "info", guild) or "ℹ️"
    sparkles = em(settings, "sparkles", guild) or "✨"

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, Banners.ROLES_PANEL)
    container.add_item(
        discord.ui.TextDisplay(
            f"**{info} 𑁉 ROLLEN-INFO**\n"
            f"{arrow2} Hier siehst du alle Rollen-Kategorien mit Live-Zahlen.\n\n"
            f"{sparkles} Unten Kategorie auswählen: **Erfolge, Level, Sonder, Teamrollen**."
        )
    )
    container.add_item(discord.ui.Separator())
    row = discord.ui.ActionRow()
    row.add_item(select)
    container.add_item(row)
    return container


def build_roles_category_view(settings, guild: discord.Guild, category: str) -> discord.ui.LayoutView:
    cat = str(category or "").lower()
    show_members = cat in {"team", "special"}
    label, header, banner, roles = _roles_for_category(settings, guild, cat)
    lines = []
    total_members = 0
    for role in roles:
        members = _non_bot_members(role)
        cnt = len(members)
        total_members += cnt
        icon = "🟢" if cnt > 0 else "⚪"
        lines.append(f"{icon} {role.mention} 𑁉 Besitzer: `x{cnt}`")
        if show_members:
            lines.append("")
            if not members:
                lines.append("`┗👤` Mitglieder: `keine`")
            else:
                shown = members[:12]
                mention_list = [m.mention for m in shown]
                rest = len(members) - len(shown)
                lines.append(f"`┗👤` Mitglieder (`{cnt}`):")
                for grp in _chunk(mention_list, 3):
                    lines.append("`   ` " + "  •  ".join(grp))
                if rest > 0:
                    lines.append(f"`   ` +`{rest}` weitere")
            lines.append("")

    empty_text = "Keine Rollen konfiguriert."
    if show_members:
        empty_text = "Keine Rollen gefunden. Prüfe `role-info.team_role_ids` / `role-info.special_role_ids` und ob die IDs zu diesem Server gehören."
    roles_block = _boxed(lines, empty_text)
    avg_members = round((total_members / len(roles)), 1) if roles else 0
    stats_block = (
        f"┏`📦` - Rollen in Kategorie: **{len(roles)}**\n"
        f"┣`👥` - Summierte Besitzer: **{total_members}**\n"
        f"┗`📈` - Ø Besitzer pro Rolle: **{avg_members}**"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, banner)
    container.add_item(
        discord.ui.TextDisplay(
            f"**{header}**\n"
            f"`📚` Kategorie: **{label}**"
        )
    )
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**`🎭` Rollenübersicht**\n{roles_block}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**`📊` Live-Stats**\n{stats_block}"))

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view

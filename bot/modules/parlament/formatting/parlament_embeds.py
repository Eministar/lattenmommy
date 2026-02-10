import discord
from discord.utils import format_dt
from datetime import datetime
from bot.utils.emojis import em
from bot.utils.assets import Banners


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


def _add_banner(container: discord.ui.Container, banner: str):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=banner)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _status_emoji(status: discord.Status | str | None) -> str:
    if status == "online" or status == discord.Status.online:
        return "🟢"
    if status == "dnd" or status == discord.Status.dnd:
        return "🔴"
    if status == "idle" or status == discord.Status.idle:
        return "🟠"
    return "⚫"


def _status_order(status: discord.Status | str | None) -> int:
    if status == "online" or status == discord.Status.online:
        return 0
    if status == "dnd" or status == discord.Status.dnd:
        return 1
    if status == "idle" or status == discord.Status.idle:
        return 2
    return 3


def _stats_line(stats: tuple[int, int] | None) -> str:
    elected = int(stats[0]) if stats else 0
    candidated = int(stats[1]) if stats else 0
    return f"Gewählt: **{elected}** • Kandidiert: **{candidated}**"


def _member_line(member: discord.Member, stats: tuple[int, int] | None) -> str:
    raw = getattr(member, "raw_status", None) or getattr(member, "status", None)
    emoji = _status_emoji(raw)
    return f"{emoji} {member.mention} — {_stats_line(stats)}"


def build_parliament_panel_container(
    settings,
    guild: discord.Guild | None,
    candidates: list[discord.Member],
    members: list[discord.Member],
    stats_map: dict[int, tuple[int, int]],
    fixed_members: list[discord.Member] | None = None,
    updated_at: datetime | None = None,
):
    palace = em(settings, "palace", guild) or "🏛️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    info = em(settings, "info", guild) or "ℹ️"

    fixed_members = fixed_members or []
    candidates_sorted = sorted(
        candidates,
        key=lambda m: (_status_order(getattr(m, "raw_status", None) or getattr(m, "status", None)), m.display_name.lower()),
    )
    members_sorted = sorted(
        members,
        key=lambda m: (_status_order(getattr(m, "raw_status", None) or getattr(m, "status", None)), m.display_name.lower()),
    )

    cand_lines = [
        _member_line(m, stats_map.get(int(m.id))) for m in candidates_sorted
    ]
    mem_lines = [
        _member_line(m, stats_map.get(int(m.id))) for m in members_sorted
    ]
    fixed_lines = [
        _member_line(m, stats_map.get(int(m.id))) for m in fixed_members
    ]

    if not cand_lines:
        cand_lines = ["—"]
    if not mem_lines:
        mem_lines = ["—"]
    if not fixed_lines:
        fixed_lines = ["—"]

    intro = (
        f"{arrow2} Repräsentieren die Members in unseren Team-Sitzungen, planen Events\n"
        f"{arrow2} und koordinieren die BKT-Zeitung. Amtszeit: **2 Wochen**."
    )
    leaders_block = "\n".join(fixed_lines)
    cand_block = "\n".join(cand_lines)
    mem_block = "\n".join(mem_lines)
    desc = (
        f"{intro}\n\n"
        f"┏`👑` - Leitung: {len(fixed_members)}\n"
        f"┣`🧩` - Kandidaten: {len(candidates)}\n"
        f"┗`👥` - Mitglieder: {len(members)}\n\n"
        f"{info} Live-Status"
    )

    header = f"**{palace} 𑁉 PARLAMENT – STATUS**"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, Banners.PARLIAMENT)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**Feste Mitglieder (Leitung)**\n{leaders_block}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**Kandidaten ({len(candidates)})**\n{cand_block}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**Mitglieder ({len(members)})**\n{mem_block}"))
    if updated_at:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"Aktualisiert: {format_dt(updated_at, style='t')}"))
    return container


def build_parliament_panel_embed(
    settings,
    guild: discord.Guild | None,
    candidates: list[discord.Member],
    members: list[discord.Member],
    stats_map: dict[int, tuple[int, int]],
    fixed_members: list[discord.Member] | None = None,
    updated_at: datetime | None = None,
):
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        build_parliament_panel_container(
            settings,
            guild,
            candidates,
            members,
            stats_map,
            fixed_members=fixed_members,
            updated_at=updated_at,
        )
    )
    return view


def _bar(pct: int) -> str:
    full = "█" * max(1, int(pct / 10))
    empty = "░" * (10 - len(full))
    return f"`{full}{empty}` {pct}%"


def build_parliament_vote_container(
    settings,
    guild: discord.Guild | None,
    candidates: list[discord.Member],
    counts: dict[int, int],
    status_label: str,
    created_at: datetime | None = None,
):
    palace = em(settings, "palace", guild) or "🏛️"
    arrow2 = em(settings, "arrow2", guild) or "»"

    total_votes = sum(counts.values())
    lines = []
    for idx, m in enumerate(candidates, start=1):
        votes = int(counts.get(int(m.id), 0))
        pct = int((votes / total_votes) * 100) if total_votes else 0
        lines.append(f"**{idx}. {m.display_name}**\n{_bar(pct)} • {votes} Stimme(n)")

    desc = (
        f"{arrow2} Bitte wähle deinen Kandidaten. Jede Person darf **einmal** abstimmen.\n\n"
        + "\n\n".join(lines)
    )

    header = f"**{palace} 𑁉 PARLAMENT – VOTUM • {status_label}**"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container, Banners.ELECTION)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    if created_at:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"Start: {format_dt(created_at, style='f')}"))
    return container


def build_parliament_vote_embed(
    settings,
    guild: discord.Guild | None,
    candidates: list[discord.Member],
    counts: dict[int, int],
    status_label: str,
    created_at: datetime | None = None,
):
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        build_parliament_vote_container(
            settings,
            guild,
            candidates,
            counts,
            status_label,
            created_at=created_at,
        )
    )
    return view

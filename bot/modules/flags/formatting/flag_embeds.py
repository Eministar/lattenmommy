from __future__ import annotations

from datetime import datetime

import discord
from discord.utils import format_dt

from bot.utils.assets import Banners
from bot.utils.emojis import em


def _color(settings, guild: discord.Guild | None) -> int:
    gid = guild.id if guild else 0
    raw = str(settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
    try:
        return int(raw, 16)
    except Exception:
        return 0xB16B91


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.FLAGS)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def build_dashboard_view(settings, guild: discord.Guild | None, stats: dict, buttons: list[discord.ui.Button]):
    arrow2 = em(settings, "arrow2", guild) or "»"
    info = em(settings, "info", guild) or "ℹ️"
    header = f"**{info} 𑁉 FLAGGENQUIZ**"
    desc = (
        f"{arrow2} Lerne Länder über echte Flaggenbilder im schnellen Quiz-Modus.\n"
        f"{arrow2} Starte Normal, Easy, Daily oder Custom und sammle Punkte + Streaks.\n"
        f"{arrow2} Custom: Einsatz setzen, 15s Zeit, richtig = doppelt zurueck, falsch = Einsatz weg.\n\n"
        f"┏`👥` - Spieler: **{int(stats.get('players', 0))}**\n"
        f"┣`🎮` - Runden: **{int(stats.get('rounds', 0))}**\n"
        f"┣`🔥` - Beste Streak: **{int(stats.get('best_streak', 0))}**\n"
        f"┗`🥇` - Leader: {stats.get('leader', 'Noch kein Eintrag')}"
    )
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    container.add_item(discord.ui.Separator())
    for i in range(0, len(buttons), 5):
        row = discord.ui.ActionRow()
        for btn in buttons[i:i + 5]:
            row.add_item(btn)
        container.add_item(row)
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_round_embed(
    settings,
    guild: discord.Guild | None,
    target_id: int,
    country_name: str,
    code: str,
    flag_url: str,
    mode: str,
    end_at: datetime | None = None,
    wager_points: int = 0,
    time_limit_seconds: int = 30,
    asked: int = 0,
    correct: int = 0,
    wrong: int = 0,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    mode_text = {"normal": "Normal", "easy": "Easy", "daily": "Daily", "bet": "Custom"}.get(str(mode), "Normal")
    title = f"**🎯 𑁉 FLAGGENRÄTSEL ({mode_text})**"
    timer_text = f"**{int(time_limit_seconds)}s**"
    if end_at is not None:
        try:
            timer_text = f"{format_dt(end_at, style='R')} ({format_dt(end_at, style='t')})"
        except Exception:
            timer_text = f"**{int(time_limit_seconds)}s**"

    wager_line = ""
    if int(wager_points) > 0:
        wager_line = f"┣`💰` - Einsatz: **{int(wager_points)}** (Gewinn bei richtig: **+{int(wager_points) * 2}**)\n"
    body = (
        f"{arrow2} Antworte mit dem Ländernamen.\n\n"
        f"┏`👤` - Für: <@{int(target_id)}>\n"
        f"┣`🌍` - Flagge: **Unbekannt**\n"
        f"┣`📈` - Diese Flagge: gefragt **{int(asked)}x**\n"
        f"{wager_line}"
        f"┣`✅` - Richtig: **{int(correct)}**\n"
        f"┣`❌` - Falsch: **{int(wrong)}**\n"
        f"┗`⏱️` - Zeitlimit: {timer_text}"
    )
    emb = discord.Embed(title=title, description=body, color=_color(settings, guild))
    emb.set_image(url=str(flag_url))
    return emb


def build_result_embed(
    settings,
    guild: discord.Guild | None,
    correct: bool,
    user_id: int,
    country_name: str,
    code: str,
    flag_url: str,
    points_gained: int,
    total_points: int,
    current_streak: int,
    asked: int = 0,
    right_total: int = 0,
    wrong_total: int = 0,
):
    title = "✅ 𑁉 RICHTIG!" if correct else "❌ 𑁉 FALSCH!"
    if correct:
        desc = (
            f"┏`👤` - User: <@{int(user_id)}>\n"
            f"┣`🌍` - Land: **{country_name}** ({code})\n"
            f"┣`💎` - Punkte: **+{int(points_gained)}** (Gesamt: **{int(total_points)}**)\n"
            f"┣`🔥` - Streak: **{int(current_streak)}**\n"
            f"┗`📊` - Flaggen-Stats: **{int(asked)}** gefragt • ✅ {int(right_total)} • ❌ {int(wrong_total)}"
        )
    else:
        points_line = f"┣`💎` - Gesamtpunkte: **{int(total_points)}**\n"
        if int(points_gained) < 0:
            points_line = f"┣`💎` - Punkte: **{int(points_gained)}** (Gesamt: **{int(total_points)}**)\n"
        desc = (
            f"┏`👤` - User: <@{int(user_id)}>\n"
            f"┣`🌍` - Lösung: **{country_name}** ({code})\n"
            f"{points_line}"
            f"┣`🔥` - Aktuelle Streak: **{int(current_streak)}**\n"
            f"┗`📊` - Flaggen-Stats: **{int(asked)}** gefragt • ✅ {int(right_total)} • ❌ {int(wrong_total)}"
        )
    emb = discord.Embed(title=title, description=desc, color=_color(settings, guild))
    emb.set_image(url=str(flag_url))
    return emb


def build_leaderboard_embed(settings, guild: discord.Guild, rows: list[tuple]) -> discord.Embed:
    if not rows:
        return discord.Embed(
            title="🏆 𑁉 LEADERBOARD",
            description="Noch keine Einträge.",
            color=_color(settings, guild),
        )
    lines = []
    for i, row in enumerate(rows, 1):
        uid = int(row[0])
        points = int(row[1] or 0)
        member = guild.get_member(uid)
        name = member.display_name if member else str(uid)
        lines.append(f"`#{i}` **{name}** — **{points}** Punkte")
    return discord.Embed(
        title="🏆 𑁉 LEADERBOARD",
        description="\n".join(lines),
        color=_color(settings, guild),
    )


def build_streaks_embed(settings, guild: discord.Guild, rows: list[tuple]) -> discord.Embed:
    if not rows:
        return discord.Embed(
            title="🔥 𑁉 STREAKS",
            description="Noch keine Einträge.",
            color=_color(settings, guild),
        )
    lines = []
    for i, row in enumerate(rows, 1):
        uid = int(row[0])
        cur = int(row[1] or 0)
        best = int(row[2] or 0)
        member = guild.get_member(uid)
        name = member.display_name if member else str(uid)
        lines.append(f"`#{i}` **{name}** — Streak **{cur}** (Best **{best}**)")
    return discord.Embed(
        title="🔥 𑁉 STREAKS",
        description="\n".join(lines),
        color=_color(settings, guild),
    )

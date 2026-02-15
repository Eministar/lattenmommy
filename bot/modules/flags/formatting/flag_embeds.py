from __future__ import annotations

import discord

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
        f"{arrow2} Echte Flaggenbilder, bessere Auswertung, sauberes Design.\n\n"
        f"┏`👥` - Spieler: **{int(stats.get('players', 0))}**\n"
        f"┣`🎮` - Runden: **{int(stats.get('rounds', 0))}**\n"
        f"┣`🔥` - Beste Streak: **{int(stats.get('best_streak', 0))}**\n"
        f"┗`🥇` - Leader: {stats.get('leader', 'Noch kein Eintrag')}"
    )
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    container.add_item(discord.ui.Separator())
    row = discord.ui.ActionRow()
    for btn in buttons:
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
    mode: str,
    asked: int = 0,
    correct: int = 0,
    wrong: int = 0,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    mode_text = {"normal": "Normal", "easy": "Easy", "daily": "Daily"}.get(str(mode), "Normal")
    title = f"**🎯 𑁉 FLAGGENRÄTSEL ({mode_text})**"
    body = (
        f"{arrow2} Antworte mit dem Ländernamen.\n\n"
        f"┏`👤` - Für: <@{int(target_id)}>\n"
        f"┣`🌍` - Lösung-Code: **{code}**\n"
        f"┣`📈` - Diese Flagge: gefragt **{int(asked)}x**\n"
        f"┣`✅` - Richtig: **{int(correct)}**\n"
        f"┣`❌` - Falsch: **{int(wrong)}**\n"
        f"┗`⏱️` - Zeitlimit: **30s**"
    )
    emb = discord.Embed(title=title, description=body, color=_color(settings, guild))
    emb.set_image(url=f"https://flagcdn.com/w1024/{code.lower()}.png")
    emb.set_footer(text=f"Lösung intern: {country_name}")
    return emb


def build_result_embed(
    settings,
    guild: discord.Guild | None,
    correct: bool,
    user_id: int,
    country_name: str,
    code: str,
    points: int,
    streak: int,
    asked: int = 0,
    right_total: int = 0,
    wrong_total: int = 0,
):
    title = "✅ 𑁉 RICHTIG!" if correct else "❌ 𑁉 FALSCH!"
    if correct:
        desc = (
            f"┏`👤` - User: <@{int(user_id)}>\n"
            f"┣`🌍` - Land: **{country_name}** ({code})\n"
            f"┣`💎` - Punkte: **+{int(points)}**\n"
            f"┣`🔥` - Streak: **{int(streak)}**\n"
            f"┗`📊` - Flaggen-Stats: **{int(asked)}** gefragt • ✅ {int(right_total)} • ❌ {int(wrong_total)}"
        )
    else:
        desc = (
            f"┏`👤` - User: <@{int(user_id)}>\n"
            f"┣`🌍` - Lösung: **{country_name}** ({code})\n"
            f"┣`🔥` - Streak wurde zurückgesetzt\n"
            f"┗`📊` - Flaggen-Stats: **{int(asked)}** gefragt • ✅ {int(right_total)} • ❌ {int(wrong_total)}"
        )
    emb = discord.Embed(title=title, description=desc, color=_color(settings, guild))
    emb.set_image(url=f"https://flagcdn.com/w1024/{code.lower()}.png")
    return emb

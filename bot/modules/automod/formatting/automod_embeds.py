from __future__ import annotations

import discord


def _color(settings, guild: discord.Guild | None) -> int:
    gid = guild.id if guild else 0
    raw = str(settings.get_guild(gid, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
    try:
        return int(raw, 16)
    except Exception:
        return 0xB16B91


def build_blacklist_delete_embed(settings, guild: discord.Guild, user: discord.abc.User, total_hits: int) -> discord.Embed:
    emb = discord.Embed(
        title="🛡️ 𑁉 AutoMod",
        description=(
            f"{user.mention} deine Nachricht wurde gelöscht, "
            f"weil sie ein vulgäres / gesperrtes Wort enthält.\n"
            f"Bitte halte den Chat sauber.\n\n"
            f"`📌` Vermerk für dich: **{int(total_hits)}**"
        ),
        color=_color(settings, guild),
    )
    return emb


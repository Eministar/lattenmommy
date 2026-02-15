from __future__ import annotations

import discord

from bot.utils.assets import Banners
from bot.utils.emojis import em


def _color(settings, guild: discord.Guild | None) -> int:
    try:
        val = settings.get_guild(guild.id, "design.accent_color", "#B16B91") if guild else settings.get("design.accent_color", "#B16B91")
    except Exception:
        val = "#B16B91"
    raw = str(val or "#B16B91").replace("#", "").strip()
    try:
        return int(raw, 16)
    except Exception:
        return 0xB16B91


def _module_banner(module_key: str) -> str:
    mapping = {
        "tickets": Banners.SUPPORT,
        "applications": Banners.APPLICATION,
        "suggestions": Banners.SUGGESTION_PANEL,
        "news": Banners.BOT_BANNER,
        "roles": Banners.ROLES_PANEL,
        "custom_roles": Banners.ROLES_OTHER,
        "birthdays": Banners.BIRTHDAY_BANNER,
        "giveaways": Banners.GIVEAWAY,
        "polls": Banners.POLL,
        "invites": Banners.INVITE,
        "tempvoice": Banners.TEMPVOICE,
        "flags": Banners.FLAGS,
        "counting": Banners.COUNTING,
        "parlament": Banners.PARLIAMENT,
        "seelsorge": Banners.SEELSORGE,
        "beichte": Banners.BEICHTE,
        "ping": Banners.PING,
    }
    return mapping.get(str(module_key), Banners.BOT_BANNER)


def build_hub_embed(settings, guild: discord.Guild | None, module_count: int) -> discord.Embed:
    info = em(settings, "info", guild) or "ℹ️"
    emb = discord.Embed(
        title=f"{info} 𑁉 SERVER GUIDE",
        description=(
            "Willkommen im Server-Guide.\n"
            "Hier bekommst du pro Modul einen eigenen Thread mit allen Commands und einer Erklärung.\n\n"
            f"Aktive Module: **{int(module_count)}**"
        ),
        color=_color(settings, guild),
    )
    emb.set_image(url=Banners.BOT_BANNER)
    return emb


def build_module_embed(settings, guild: discord.Guild | None, module_title: str, module_key: str, command_lines: list[str], note: str | None = None) -> discord.Embed:
    chat = em(settings, "chat", guild) or "💬"
    desc = [
        f"**{chat} 𑁉 MODUL: {module_title.upper()}**",
        "",
        "Hier findest du alle verfügbaren Slash- und Prefix-Commands.",
    ]
    if note:
        desc.extend(["", str(note)])
    desc.extend(["", "**Commands**", "\n".join(command_lines) if command_lines else "Keine Commands gefunden."])
    emb = discord.Embed(
        title=f"Guide • {module_title}",
        description="\n".join(desc)[:4000],
        color=_color(settings, guild),
    )
    emb.set_image(url=_module_banner(module_key))
    return emb

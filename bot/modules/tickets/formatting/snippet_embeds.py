import discord
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


def _wrap(container: discord.ui.Container) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_snippet_embed(settings, guild: discord.Guild | None, key: str, title: str, body: str):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = f"{arrow2} {body}"
    header = f"**{info} {title} · {key}**"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    return _wrap(container)


def build_snippet_list_embed(settings, guild: discord.Guild | None, items: list[tuple[str, str]]):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    if not items:
        desc = f"{arrow2} Keine Snippets konfiguriert."
    else:
        lines = [f"• `{k}` - {title}" for k, title in items]
        desc = f"{arrow2} Verfügbare Snippets:\n\n" + "\n".join(lines)
    header = f"**{info} Text-Snippets**"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    return _wrap(container)

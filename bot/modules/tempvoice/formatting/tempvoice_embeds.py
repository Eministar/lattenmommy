import discord
from bot.utils.emojis import em
from bot.utils.assets import Banners


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


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.TEMPVOICE)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _wrap(container: discord.ui.Container) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def _region_label(region: str | None) -> str:
    if not region or str(region).lower() in {"none", "auto", "automatic"}:
        return "Automatisch"
    return str(region).replace("_", "-")


def build_tempvoice_panel_embed(
    settings,
    guild: discord.Guild | None,
    owner: discord.Member,
    channel: discord.VoiceChannel,
    locked: bool,
    private: bool,
):
    return _wrap(build_tempvoice_panel_container(settings, guild, owner, channel, locked, private))


def build_tempvoice_panel_container(
    settings,
    guild: discord.Guild | None,
    owner: discord.Member,
    channel: discord.VoiceChannel,
    locked: bool,
    private: bool,
):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    region = _region_label(getattr(channel, "rtc_region", None))
    limit = int(channel.user_limit or 0)
    bitrate = int(channel.bitrate or 0) // 1000
    status_lock = "Gesperrt" if locked else "Offen"
    status_priv = "Privat" if private else "Oeffentlich"

    desc = (
        f"{arrow2} Hier steuerst du deinen Temp-Voice. Alle Aenderungen gelten sofort.\n\n"
        f"┏`👤` - Owner: {owner.mention}\n"
        f"┣`🔊` - Channel: {channel.mention}\n"
        f"┣`🔒` - Status: **{status_lock}** / **{status_priv}**\n"
        f"┣`👥` - Limit: **{limit if limit else 'Unbegrenzt'}**\n"
        f"┣`📡` - Region: **{region}**\n"
        f"┗`🎛️` - Bitrate: **{bitrate} kbps**\n\n"
        "Nutze die Buttons und Menues unten, um User zu verwalten oder den Channel zu "
        "anpassen."
    )
    header = f"**{info} 𑁉 TEMP-VOICE PANEL**"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    return container


def build_tempvoice_invite_embed(
    settings,
    guild: discord.Guild | None,
    owner: discord.Member,
    channel: discord.VoiceChannel,
):
    return _wrap(build_tempvoice_invite_container(settings, guild, owner, channel))


def build_tempvoice_invite_container(
    settings,
    guild: discord.Guild | None,
    owner: discord.Member,
    channel: discord.VoiceChannel,
):
    love = em(settings, "discord_love", guild) or "💜"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = (
        f"{arrow2} {owner.mention} hat dich in einen Temp-Voice eingeladen.\n\n"
        f"┏`🔊` - Channel: {channel.mention}\n"
        f"┗`👤` - Owner: **{owner.display_name}**\n\n"
        "Du kannst jetzt joinen. Viel Spass!"
    )
    header = f"**{love} 𑁉 VOICE-EINLADUNG**"
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    return container

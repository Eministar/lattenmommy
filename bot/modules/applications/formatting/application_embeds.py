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


def _apply_banner(emb: discord.Embed):
    emb.set_image(url=Banners.APPLICATION)


def build_application_embed(settings, guild: discord.Guild | None, user: discord.User, questions: list[str], answers: list[str]):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    desc = f"{arrow2} Neue Bewerbung eingegangen. Bitte prüft die Antworten sorgfältig."
    emb = discord.Embed(title=f"{info} 𑁉 BEWERBUNG", description=desc, color=_color(settings, guild))
    emb.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    _apply_banner(emb)
    for idx, q in enumerate(questions):
        a = answers[idx] if idx < len(answers) else "-"
        emb.add_field(name=f"{idx + 1}. {q}", value=a[:1024] or "-", inline=False)
    _footer(emb, settings, guild)
    return emb


def build_application_dm_embed(settings, guild: discord.Guild | None, questions: list[str]):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    lines = [f"{i+1}. {q}" for i, q in enumerate(questions)]
    desc = f"{arrow2} Bitte beantworte die folgenden Fragen – klar und ehrlich.\n\n" + "\n".join(lines)
    emb = discord.Embed(title=f"{info} 𑁉 BEWERBUNG STARTEN", description=desc, color=_color(settings, guild))
    _apply_banner(emb)
    _footer(emb, settings, guild)
    return emb


def build_application_panel_embed(
    settings,
    guild: discord.Guild | None,
    total: int,
    open_: int,
):
    pen = em(settings, "pen", guild) or "📝"
    arrow2 = em(settings, "arrow2", guild) or "»"
    sparkles = em(settings, "sparkles", guild) or "✨"
    info = em(settings, "info", guild) or "ℹ️"
    emb = discord.Embed(
        title=f"{pen} 𑁉 BEWERBUNGS-PANEL",
        description=(
            f"{arrow2} Du willst Teil des Teams werden? Starte deine Bewerbung direkt hier.\n\n"
            f"{sparkles} **Jetzt bewerben** – kurz, strukturiert und im Design eures Servers."
        ),
        color=_color(settings, guild),
    )
    _apply_banner(emb)
    emb.add_field(
        name="Ablauf",
        value=(
            "1) Button klicken\n"
            "2) Fragen beantworten\n"
            "3) Wir prüfen die Bewerbung\n"
            "4) Rückmeldung im Thread"
        ),
        inline=False,
    )
    emb.add_field(
        name=f"{info} Live-Stats",
        value=(
            f"Bewerbungen gesamt: **{total}**\n"
            f"Offen: **{open_}**"
        ),
        inline=False,
    )
    if guild and guild.icon:
        emb.set_thumbnail(url=guild.icon.url)
    _footer(emb, settings, guild)
    return emb


def build_application_panel_container(
    settings,
    guild: discord.Guild | None,
    total: int,
    open_: int,
    button: discord.ui.Button,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    pen = em(settings, "pen", guild) or "📝"
    sparkles = em(settings, "sparkles", guild) or "✨"
    info = em(settings, "info", guild) or "ℹ️"

    header = f"**{pen} 𑁉 BEWERBUNGS-PANEL**"
    intro = f"{arrow2} Du willst Teil des Teams werden? Starte deine Bewerbung direkt hier."
    cta = f"{sparkles} **Jetzt bewerben** – kurz, strukturiert und im Design eures Servers."
    flow = (
        "1) Button klicken\n"
        "2) Fragen beantworten\n"
        "3) Wir prüfen die Bewerbung\n"
        "4) Rückmeldung im Thread"
    )
    stats_block = (
        f"Bewerbungen gesamt: **{total}**\n"
        f"Offen: **{open_}**"
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    container.add_item(discord.ui.TextDisplay(f"{header}\n{intro}\n\n{cta}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**Ablauf**\n{flow}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**{info} Live-Stats**\n{stats_block}"))
    row = discord.ui.ActionRow()
    row.add_item(button)
    container.add_item(row)
    return container


def build_application_followup_dm_embed(
    settings,
    guild: discord.Guild | None,
    staff: discord.Member | None,
    question: str,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    chat = em(settings, "chat", guild) or "💬"
    title = f"{chat} 𑁉 WICHTIGE RÜCKFRAGE"
    desc = (
        f"{arrow2} Wir haben noch eine kurze Rückfrage zu deiner Bewerbung.\n"
        "Bitte antworte direkt hier in der DM."
    )
    emb = discord.Embed(title=title, description=desc, color=_color(settings, guild))
    _apply_banner(emb)
    emb.add_field(name="FRAGE", value=f"**{question.strip()}**", inline=False)
    emb.add_field(
        name="DEIN BEDÜRFNIS",
        value="Wir möchten deine Bewerbung bestmöglich verstehen – nimm dir kurz Zeit für deine Antwort.",
        inline=False,
    )
    if staff:
        emb.set_author(name=staff.display_name, icon_url=staff.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_application_followup_answer_embed(
    settings,
    guild: discord.Guild | None,
    user: discord.User,
    question: str,
    answer: str,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    pen = em(settings, "pen", guild) or "📝"
    desc = f"{arrow2} Rückfrage beantwortet von {user.mention}."
    emb = discord.Embed(title=f"{pen} 𑁉 RÜCKFRAGE BEANTWORTET", description=desc, color=_color(settings, guild))
    _apply_banner(emb)
    emb.add_field(name="FRAGE", value=question.strip()[:1024], inline=False)
    emb.add_field(name="ANTWORT", value=answer.strip()[:1024], inline=False)
    emb.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    _footer(emb, settings, guild)
    return emb


def build_application_decision_embed(
    settings,
    guild: discord.Guild | None,
    accepted: bool,
    staff: discord.Member | None,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    badge = em(settings, "badge", guild) or ("✅" if accepted else "⛔")
    status_text = "ANGENOMMEN" if accepted else "ABGELEHNT"
    desc = f"{arrow2} Entscheidung wurde gespeichert: **{status_text}**."
    emb = discord.Embed(title=f"{badge} 𑁉 BEWERBUNG {status_text}", description=desc, color=_color(settings, guild))
    _apply_banner(emb)
    if staff:
        emb.set_author(name=staff.display_name, icon_url=staff.display_avatar.url)
    _footer(emb, settings, guild)
    return emb

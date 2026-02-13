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


def _clip(text: str, limit: int) -> str:
    t = str(text or "").strip()
    if len(t) <= limit:
        return t
    return t[: max(0, limit - 3)].rstrip() + "..."


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


def _add_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.APPLICATION)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _add_panel_banner(container: discord.ui.Container):
    try:
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=Banners.APPLICATION)
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
    except Exception:
        pass


def _resolve_user_line(user: discord.User | int | None) -> tuple[int, str]:
    try:
        user_id = int(getattr(user, "id", 0) or int(user or 0))
    except Exception:
        user_id = 0
    return user_id, f"<@{user_id}>" if user_id else "—"


def _qa_block(questions: list[str], answers: list[str]) -> str:
    lines = []
    for idx, q in enumerate(questions):
        a = answers[idx] if idx < len(answers) else "-"
        clean_q = str(q or "").strip() or "Frage"
        clean_a = _clip(str(a or "-").strip(), 900) or "-"
        lines.append(f"**{idx + 1}. {clean_q}**\n{clean_a}")
    return "\n\n".join(lines) if lines else "—"


def build_application_container(settings, guild: discord.Guild | None, user: discord.User | int, questions: list[str], answers: list[str]):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    header = f"**{info} 𑁉 BEWERBUNG**"
    desc = f"{arrow2} Neue Bewerbung eingegangen. Bitte prüft die Antworten sorgfältig."

    user_id, user_line = _resolve_user_line(user)
    meta = (
        f"┏`👤` - Von: {user_line}\n"
        f"┗`🧾` - Antworten: {len(answers)}/{len(questions)}"
    )
    qa_text = _qa_block(questions, answers)

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}\n\n{meta}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(qa_text))
    return container


def build_application_embed(settings, guild: discord.Guild | None, user: discord.User | int, questions: list[str], answers: list[str]):
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(build_application_container(settings, guild, user, questions, answers))
    return view


def build_application_dm_embed(settings, guild: discord.Guild | None, questions: list[str]):
    info = em(settings, "info", guild) or "ℹ️"
    arrow2 = em(settings, "arrow2", guild) or "»"
    lines = [f"{i+1}. {q}" for i, q in enumerate(questions)]
    header = f"**{info} 𑁉 BEWERBUNG STARTEN**"
    desc = f"{arrow2} Bitte beantworte die folgenden Fragen – klar und ehrlich.\n\n" + "\n".join(lines)
    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


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
    green = em(settings, "green", guild) or "🟢"
    orange = em(settings, "orange", guild) or "🟠"

    header = f"**{pen} 𑁉 BEWERBUNGS-PANEL**"
    intro = f"{arrow2} Du willst Teil des Teams werden? Starte deine Bewerbung direkt hier."
    cta = f"{sparkles} **Bewerbung starten** und die Fragen sauber beantworten."
    flow = (
        "┏`🖱️` - Button klicken\n"
        "┣`🧾` - Fragen ausfüllen\n"
        "┣`🔎` - Team prüft deine Antworten\n"
        "┗`📬` - Entscheidung im Bewerbungs-Thread"
    )
    stats_block = (
        f"┏`📦` - Bewerbungen gesamt: **{total}**\n"
        f"┣`{orange}` - Offen: **{open_}**\n"
        f"┗`{green}` - Bearbeitet: **{max(0, int(total) - int(open_))}**"
    )
    note_block = (
        f"{info} **Hinweis**\n"
        "Unvollständige oder leere Antworten verzögern die Prüfung."
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_panel_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{intro}\n\n{cta}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**Ablauf**\n{flow}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"**{info} Live-Stats**\n{stats_block}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(note_block))
    container.add_item(discord.ui.Separator())
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
    header = f"**{chat} 𑁉 WICHTIGE RÜCKFRAGE**"
    desc = (
        f"{arrow2} Wir haben noch eine kurze Rückfrage zu deiner Bewerbung.\n"
        "Bitte antworte direkt hier in der DM."
    )
    question_text = str(question or "").strip() or "—"
    body = (
        f"**FRAGE**\n{question_text}\n\n"
        "**DEIN BEDÜRFNIS**\nWir möchten deine Bewerbung bestmöglich verstehen – nimm dir kurz Zeit für deine Antwort."
    )

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(body))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_application_followup_answer_embed(
    settings,
    guild: discord.Guild | None,
    user: discord.User,
    question: str,
    answer: str,
    staff_id: int | None = None,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    pen = em(settings, "pen", guild) or "📝"
    header = f"**{pen} 𑁉 RÜCKFRAGE BEANTWORTET**"
    desc = f"{arrow2} Rückfrage beantwortet von {user.mention}."
    if staff_id:
        desc = f"{desc}\n{arrow2} Rückfrage gestellt von <@{int(staff_id)}>"
    q_text = _clip(str(question or "").strip(), 900) or "—"
    a_text = _clip(str(answer or "").strip(), 900) or "—"
    body = f"**FRAGE**\n{q_text}\n\n**ANTWORT**\n{a_text}"

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(body))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def build_application_decision_embed(
    settings,
    guild: discord.Guild | None,
    accepted: bool,
    staff: discord.Member | None,
):
    arrow2 = em(settings, "arrow2", guild) or "»"
    badge = em(settings, "badge", guild) or ("✅" if accepted else "⛔")
    status_text = "ANGENOMMEN" if accepted else "ABGELEHNT"
    header = f"**{badge} 𑁉 BEWERBUNG {status_text}**"
    desc = f"{arrow2} Entscheidung wurde gespeichert: **{status_text}**."
    who = staff.mention if staff else "—"
    meta = f"┗`👤` - Entscheider: {who}"

    container = discord.ui.Container(accent_colour=_color(settings, guild))
    _add_banner(container)
    container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}\n\n{meta}"))
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view

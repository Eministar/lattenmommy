import re
import discord
from datetime import datetime, timezone

from bot.utils.perms import is_staff
from bot.tickets.views import SummaryView, RatingView
from bot.utils.formatting import (
    build_summary_embed,
    build_user_message_embed,
    build_dm_ticket_created_embed,
    build_dm_message_appended_embed,
    build_dm_staff_reply_embed,
    build_dm_ticket_closed_embed,
    build_dm_rating_thanks_embed,
    build_thread_status_embed,
    build_thread_rating_embed,
)

_USER_ID_RE = re.compile(r"User-ID:\s*(\d{15,20})")


def _truncate(s: str, limit: int) -> str:
    if not s:
        return ""
    s = str(s)
    return s if len(s) <= limit else s[: limit - 3] + "..."


def parse_int_color(settings) -> int:
    v = str(settings.get("design.accent_color", "#B16B91") or "").replace("#", "").strip()
    try:
        return int(v, 16)
    except Exception:
        return 0xB16B91

def _extract_discord_ids(row) -> list[int]:
    ids: list[int] = []
    if not row:
        return ids

    for v in row:
        try:
            if isinstance(v, int):
                x = v
            elif isinstance(v, str) and v.isdigit():
                x = int(v)
            else:
                continue

            if 10**14 <= x <= 10**20:
                ids.append(x)
        except Exception:
            pass

    return ids

async def _ephemeral(interaction: discord.Interaction, text: str):
    try:
        await interaction.response.send_message(text, ephemeral=True)
    except discord.InteractionResponded:
        await interaction.followup.send(text, ephemeral=True)


def _normalize_ticket_row(guild_id: int, row):
    if not row:
        return None

    try:
        if len(row) >= 9 and int(row[1]) == int(guild_id):
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(row[1]),
                "user_id": int(row[2]),
                "forum_id": int(row[3]),
                "thread_id": int(row[4]),
                "summary_id": int(row[5]),
                "status": str(row[6]),
                "claimed_by": int(row[7]) if row[7] is not None else None,
                "category_key": str(row[8]) if row[8] is not None else None,
            }
    except Exception:
        pass

    try:
        if len(row) >= 7:
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(guild_id),
                "user_id": int(row[1]),
                "forum_id": 0,
                "thread_id": int(row[2]),
                "summary_id": int(row[3]),
                "status": str(row[4]),
                "claimed_by": int(row[5]) if row[5] is not None else None,
                "category_key": str(row[6]) if row[6] is not None else None,
            }
    except Exception:
        pass

    try:
        if len(row) >= 6:
            return {
                "ticket_id": int(row[0]),
                "guild_id": int(guild_id),
                "user_id": int(row[1]) if row[1] is not None else 0,
                "forum_id": 0,
                "thread_id": int(row[2]),
                "summary_id": int(row[3]),
                "status": str(row[4]),
                "claimed_by": int(row[5]) if row[5] is not None else None,
                "category_key": None,
            }
    except Exception:
        pass

    return None


def _normalize_open_ticket_row(row):
    if not row:
        return None
    try:
        if len(row) >= 6:
            return {
                "ticket_id": int(row[0]),
                "thread_id": int(row[1]),
                "summary_id": int(row[2]),
                "status": str(row[3]),
                "claimed_by": int(row[4]) if row[4] is not None else None,
                "category_key": str(row[5]) if row[5] is not None else None,
            }
    except Exception:
        pass
    try:
        if len(row) >= 2:
            return {"ticket_id": int(row[0]), "thread_id": int(row[1])}
    except Exception:
        pass
    return None


async def _resolve_user_id_from_thread(thread: discord.Thread, summary_message_id: int | None):
    if summary_message_id:
        try:
            msg = await thread.fetch_message(int(summary_message_id))
            if msg and msg.content:
                m = _USER_ID_RE.search(msg.content)
                if m:
                    return int(m.group(1))
        except Exception:
            pass

    try:
        starter = thread.starter_message
        if starter and starter.content:
            m = _USER_ID_RE.search(starter.content)
            if m:
                return int(m.group(1))
    except Exception:
        pass

    try:
        async for m in thread.history(limit=5, oldest_first=True):
            if m and m.content:
                mm = _USER_ID_RE.search(m.content)
                if mm:
                    return int(mm.group(1))
    except Exception:
        pass

    return None


class TicketService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    async def _update_summary_controls(self, thread: discord.Thread, summary_message_id: int, ticket_id: int,
                                       claimed: bool):
        if not summary_message_id:
            return
        try:
            msg = await thread.fetch_message(int(summary_message_id))
            await msg.edit(view=SummaryView(self, ticket_id=int(ticket_id), claimed=bool(claimed)))
        except Exception:
            pass

    async def _notify_user_claim_state(self, guild: discord.Guild, thread: discord.Thread, t: dict,
                                       staff: discord.Member, claimed: bool):
        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(thread, t.get("summary_id"))
        if not uid:
            return False, "user_id_missing"

        try:
            user = await self.bot.fetch_user(int(uid))
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

        color = parse_int_color(self.settings)
        ft = self.settings.get("design.footer_text", None)

        if claimed:
            title = "`🟠` 𑁉 Ticket übernommen"
            desc = (
                f"Hey! Ich bin **{staff.display_name}** und werde dir heute helfen.\n\n"
                "Antworte hier einfach per DM – das landet direkt im Ticket."
            )
        else:
            title = "`🟢` 𑁉 Ticket freigegeben"
            desc = (
                f"**{staff.display_name}** kümmert sich nicht mehr um dein Ticket.\n\n"
                "Du kannst weiter antworten – das Ticket ist wieder offen."
            )

        emb = discord.Embed(title=title, description=desc, color=color)
        emb.set_author(name=staff.display_name, icon_url=staff.display_avatar.url)
        if ft:
            emb.set_footer(text=str(ft))

        try:
            await user.send(embed=emb)
            return True, None
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    async def handle_dm(self, message: discord.Message):
        if message.author.bot:
            return

        guild_id = self.settings.get_int("bot.guild_id")
        forum_id = self.settings.get_int("bot.forum_channel_id")
        if not guild_id or not forum_id:
            return

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        allow_multi = self.settings.get_bool("ticket.allow_multiple_open_tickets_per_user", False)
        existing_row = await self.db.get_open_ticket_by_user(guild_id, message.author.id)
        existing = _normalize_open_ticket_row(existing_row)

        if existing and not allow_multi:
            thread = guild.get_thread(int(existing["thread_id"]))
            if not thread:
                try:
                    fetched = await self.bot.fetch_channel(int(existing["thread_id"]))
                    thread = fetched if isinstance(fetched, discord.Thread) else None
                except Exception:
                    thread = None

            if thread:
                await self._post_user_message(guild, thread, message.author, message.content, message.attachments)
                try:
                    await message.author.send(embed=build_dm_message_appended_embed(self.settings, guild, int(existing["ticket_id"])))
                except Exception:
                    pass

                await self.logger.emit(
                    self.bot,
                    "ticket_user_message_appended",
                    {"ticket_id": int(existing["ticket_id"]), "user_id": message.author.id},
                )
                return

        category_key = self.settings.get("ticket.default_category", "allgemeine_frage")
        await self._create_ticket(guild, message, str(category_key))

    async def _create_ticket(self, guild: discord.Guild, dm_message: discord.Message, category_key: str):
        forum_id = self.settings.get_int("bot.forum_channel_id")
        forum = guild.get_channel(forum_id)
        if not isinstance(forum, discord.ForumChannel):
            return

        user = dm_message.author
        member = guild.get_member(user.id)
        total = await self.db.get_ticket_count(user.id)

        cat_cfg = (self.settings.get("categories", {}) or {}).get(category_key, {}) or {}
        cat_label = str(cat_cfg.get("label", category_key)).upper()
        prefix = str(cat_cfg.get("thread_prefix", "•")).strip() or "•"

        tag_id = int(cat_cfg.get("forum_tag_id", 0) or 0)
        applied_tags = []
        if tag_id:
            tag = discord.utils.get(forum.available_tags, id=tag_id)
            if tag:
                applied_tags.append(tag)

        created_at = datetime.now(timezone.utc)

        support_role_id = self.settings.get_int("bot.support_role_id")
        role_mention = f"<@&{support_role_id}>" if support_role_id else ""

        content_head = f"User-ID: {user.id}\n{role_mention}".strip()

        summary_embed = build_summary_embed(
            self.settings,
            guild,
            user,
            member,
            _truncate(cat_label, 48),
            created_at=created_at,
            total_tickets=int(total),
        )

        view = SummaryView(self, ticket_id=0)

        thread_name = f"{prefix} {user.display_name}"
        created = await forum.create_thread(
            name=_truncate(thread_name, 100),
            content=content_head,
            embeds=[summary_embed],
            view=view,
            applied_tags=applied_tags,
        )

        thread = created.thread
        msg = created.message

        ticket_id = await self.db.create_ticket(
            guild_id=guild.id,
            user_id=user.id,
            forum_channel_id=forum.id,
            thread_id=thread.id,
            summary_message_id=msg.id,
            category_key=category_key,
        )

        view.ticket_id = int(ticket_id)
        try:
            await msg.edit(view=view)
        except Exception:
            pass

        await self._post_user_message(guild, thread, user, dm_message.content, dm_message.attachments)

        try:
            await user.send(embed=build_dm_ticket_created_embed(self.settings, guild, int(ticket_id), created_at))
        except Exception:
            pass

        await self.logger.emit(
            self.bot,
            "ticket_created",
            {"ticket_id": int(ticket_id), "user_id": user.id, "thread_id": thread.id, "category": category_key},
        )

    async def _post_user_message(self, guild: discord.Guild, thread: discord.Thread, user: discord.User, content: str, attachments):
        text = (content or "").strip()
        if attachments:
            links = "\n".join([a.url for a in attachments][:8])
            if links:
                text = (text + "\n\n" + links).strip()
        text = _truncate(text, 3500) if text else " "
        emb = build_user_message_embed(self.settings, guild, user, text)
        await thread.send(embed=emb)

    async def handle_staff_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not message.guild or not isinstance(message.author, discord.Member):
            return

        guild_id = self.settings.get_int("bot.guild_id")
        if not guild_id or message.guild.id != guild_id:
            return

        if not is_staff(self.settings, message.author):
            return

        if not isinstance(message.channel, discord.Thread):
            return

        forum_id = self.settings.get_int("bot.forum_channel_id")
        parent = getattr(message.channel, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return

        row = await self.db.get_ticket_by_thread(message.guild.id, message.channel.id)
        t = _normalize_ticket_row(message.guild.id, row)
        if not t:
            return

        if str(t["status"]) == "closed":
            return

        text = (message.content or "").strip()
        if self.settings.get_bool("ticket.mirror_staff_attachments", True) and message.attachments:
            links = "\n".join([a.url for a in message.attachments][:8])
            if links:
                text = (text + "\n\n" + links).strip()

        text = _truncate(text, 3500) if text else " "
        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(message.channel, t.get("summary_id"))

        if not uid:
            await self.logger.emit(self.bot, "ticket_staff_reply_failed_no_user", {"ticket_id": int(t["ticket_id"]), "thread_id": int(t["thread_id"])})
            return

        try:
            user = await self.bot.fetch_user(int(uid))
        except Exception:
            return

        try:
            emb = build_dm_staff_reply_embed(self.settings, message.guild, message.author, int(t["ticket_id"]), text)
            await user.send(embed=emb)
            dm_ok = True
            dm_error = None
        except Exception as e:
            dm_ok = False
            dm_error = f"{type(e).__name__}: {e}"

        await self.logger.emit(
            self.bot,
            "ticket_staff_reply",
            {"ticket_id": int(t["ticket_id"]), "staff_id": message.author.id, "user_id": int(uid), "dm_ok": dm_ok, "dm_error": dm_error},
        )

    async def toggle_claim(self, interaction: discord.Interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self.settings.get_int("bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        if str(t["status"]) == "closed":
            return await _ephemeral(interaction, "Ticket ist bereits geschlossen.")

        ticket_id = int(t["ticket_id"])
        claimed_by = t.get("claimed_by")

        if claimed_by and int(claimed_by) != interaction.user.id:
            return await _ephemeral(interaction, f"Schon geclaimed von <@{claimed_by}>.")

        if claimed_by and int(claimed_by) == interaction.user.id:
            await self.db.set_claim(ticket_id, None)

            try:
                emb = build_thread_status_embed(
                    self.settings,
                    interaction.guild,
                    "`🟢` Ticket freigegeben",
                    f"{interaction.user.mention} kümmert sich nicht mehr um dieses Ticket.",
                    interaction.user
                )
                await thread.send(embed=emb)
            except Exception:
                pass

            dm_ok, dm_error = await self._notify_user_claim_state(interaction.guild, thread, t, interaction.user,
                                                                  claimed=False)
            await self._update_summary_controls(thread, int(t.get("summary_id") or 0), ticket_id, claimed=False)

            await _ephemeral(interaction, "Ticket freigegeben.")
            await self.logger.emit(self.bot, "ticket_released", {
                "ticket_id": ticket_id,
                "staff_id": interaction.user.id,
                "dm_ok": dm_ok,
                "dm_error": dm_error
            })
            return

        await self.db.set_claim(ticket_id, interaction.user.id)

        try:
            emb = build_thread_status_embed(
                self.settings,
                interaction.guild,
                "`🟠` Ticket übernommen",
                f"Hey! Ich bin {interaction.user.mention} und werde dir heute helfen.",
                interaction.user
            )
            await thread.send(embed=emb)
        except Exception:
            pass

        dm_ok, dm_error = await self._notify_user_claim_state(interaction.guild, thread, t, interaction.user,
                                                              claimed=True)
        await self._update_summary_controls(thread, int(t.get("summary_id") or 0), ticket_id, claimed=True)

        await _ephemeral(interaction, "Ticket geclaimed.")
        await self.logger.emit(self.bot, "ticket_claimed", {
            "ticket_id": ticket_id,
            "staff_id": interaction.user.id,
            "dm_ok": dm_ok,
            "dm_error": dm_error
        })

    async def post_team_note(self, interaction: discord.Interaction, text: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self.settings.get_int("bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        note_text = _truncate((text or "").strip(), 3500) if text else " "

        try:
            emb = build_thread_status_embed(self.settings, interaction.guild, "📝 𑁉 TEAM-NOTIZ", note_text, interaction.user)
            await thread.send(embed=emb)
        except Exception:
            pass

        await _ephemeral(interaction, "Notiz gespeichert.")
        await self.logger.emit(self.bot, "ticket_note", {"ticket_id": int(t["ticket_id"]), "staff_id": interaction.user.id})

    async def close_ticket(self, interaction: discord.Interaction, reason: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return

        if not is_staff(self.settings, interaction.user):
            return await _ephemeral(interaction, "Keine Rechte.")

        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        if not thread:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        forum_id = self.settings.get_int("bot.forum_channel_id")
        parent = getattr(thread, "parent", None)
        if not parent or getattr(parent, "id", 0) != forum_id:
            return await _ephemeral(interaction, "Nur im Ticket-Thread.")

        row = await self.db.get_ticket_by_thread(interaction.guild.id, thread.id)
        t = _normalize_ticket_row(interaction.guild.id, row)
        if not t:
            return await _ephemeral(interaction, "Ticket nicht gefunden.")

        if str(t["status"]) == "closed":
            return await _ephemeral(interaction, "Ticket ist bereits geschlossen.")

        await self.db.close_ticket(int(t["ticket_id"]))
        closed_at = datetime.now(timezone.utc)

        rating_enabled = self.settings.get_bool("ticket.rating_enabled", True)

        uid = int(t["user_id"]) if t.get("user_id") else 0
        if not uid:
            uid = await _resolve_user_id_from_thread(thread, t.get("summary_id"))

        dm_ok = False
        dm_error = None

        if uid:
            try:
                user = await self.bot.fetch_user(int(uid))
                dm_emb = build_dm_ticket_closed_embed(self.settings, interaction.guild, int(t["ticket_id"]), closed_at, rating_enabled)
                if rating_enabled:
                    await user.send(embed=dm_emb, view=RatingView(self, int(t["ticket_id"])))
                else:
                    await user.send(embed=dm_emb)
                dm_ok = True
            except Exception as e:
                dm_ok = False
                dm_error = f"{type(e).__name__}: {e}"
        else:
            dm_ok = False
            dm_error = "user_id_missing"

        try:
            status_text = "Ticket wurde geschlossen und archiviert."
            if not dm_ok:
                status_text += "\n\n⚠️ User konnte nicht per DM erreicht werden."
            emb = build_thread_status_embed(self.settings, interaction.guild, "🔴 Ticket geschlossen", status_text, interaction.user)
            await thread.send(embed=emb)
        except Exception:
            pass

        try:
            await thread.edit(archived=True, locked=True)
        except Exception:
            pass

        await _ephemeral(interaction, "Ticket geschlossen." + ("" if dm_ok else " (User DM nicht möglich)"))

        await self.logger.emit(
            self.bot,
            "ticket_closed",
            {
                "ticket_id": int(t["ticket_id"]),
                "staff_id": interaction.user.id,
                "user_id": int(uid) if uid else int(t.get("user_id") or 0),
                "dm_ok": dm_ok,
                "dm_error": dm_error,
                "reason": reason if reason else None,
            },
        )

    async def submit_rating(self, interaction: discord.Interaction, ticket_id: int, rating: int, comment: str | None):
        row = await self.db.get_ticket(int(ticket_id))
        if not row:
            try:
                await interaction.response.send_message("Ticket nicht gefunden.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("Ticket nicht gefunden.", ephemeral=True)
            return

        if interaction.guild is not None:
            try:
                await interaction.response.send_message("Bitte nur in DMs bewerten.", ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send("Bitte nur in DMs bewerten.", ephemeral=True)
            return

        ids_in_row = _extract_discord_ids(row)

        if ids_in_row and interaction.user.id not in ids_in_row:
            await self.logger.emit(self.bot, "ticket_rating_owner_mismatch", {
                "ticket_id": int(ticket_id),
                "interaction_user_id": int(interaction.user.id),
                "ids_in_db_row": ids_in_row[:10],
            })

        await self.db.set_rating(int(ticket_id), int(rating), comment)

        guild_id = self.settings.get_int("bot.guild_id") or 0
        guild = self.bot.get_guild(guild_id) if guild_id else None

        try:
            await interaction.response.send_message(
                embed=build_dm_rating_thanks_embed(self.settings, guild, int(rating)),
                ephemeral=False
            )
        except discord.InteractionResponded:
            await interaction.followup.send(
                embed=build_dm_rating_thanks_embed(self.settings, guild, int(rating)),
                ephemeral=False
            )

        await self.logger.emit(self.bot, "ticket_rating", {
            "ticket_id": int(ticket_id),
            "user_id": int(interaction.user.id),
            "rating": int(rating),
            "comment": comment
        })

        try:
            t = _normalize_ticket_row(guild_id, row)
            if guild and t and t.get("thread_id"):
                thread = guild.get_thread(int(t["thread_id"]))
                if thread:
                    emb = build_thread_rating_embed(self.settings, guild, int(interaction.user.id), int(rating),
                                                    comment)
                    await thread.send(embed=emb)
        except Exception:
            pass

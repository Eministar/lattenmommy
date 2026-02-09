import time
import discord
from bot.core.perms import is_staff
from bot.modules.applications.formatting.application_embeds import (
    build_application_embed,
    build_application_dm_embed,
    build_application_followup_dm_embed,
    build_application_followup_answer_embed,
    build_application_decision_embed,
)
from bot.modules.applications.views.application_decision import ApplicationDecisionView


class ApplicationService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._sessions: dict[int, dict] = {}
        self._followups: dict[int, list[dict]] = {}
        self._recent_dm_users: dict[int, float] = {}

    def _mark_dm_handled(self, user_id: int):
        self._recent_dm_users[int(user_id)] = time.monotonic()

    def is_dm_reserved(self, user_id: int) -> bool:
        uid = int(user_id)
        if uid in self._sessions:
            return True
        pending = self._followups.get(uid) or []
        if pending:
            return True
        last = self._recent_dm_users.get(uid)
        if last is None:
            return False
        if time.monotonic() - last < 15:
            return True
        self._recent_dm_users.pop(uid, None)
        return False

    def _config(self) -> dict:
        return self.settings.get("applications", {}) or {}

    def _questions(self) -> list[str]:
        cfg = self._config()
        q = cfg.get("questions", [])
        if isinstance(q, list) and q:
            return [str(x) for x in q][:5]
        return [
            "Warum möchtest du dich bewerben?",
            "Wie viel Erfahrung hast du?",
            "Wie alt bist du?",
            "Was sind deine Stärken?",
            "Wann hast du Zeit?",
        ]

    async def has_open_ticket(self, guild_id: int, user_id: int) -> bool:
        try:
            row = await self.db.get_open_ticket_by_user(int(guild_id), int(user_id))
            if row:
                return True
            row2 = await self.db.get_open_ticket_by_participant(int(guild_id), int(user_id))
            return bool(row2)
        except Exception:
            return False

    async def start_dm_flow(self, user: discord.User, guild: discord.Guild | None):
        questions = self._questions()
        self._sessions[user.id] = {"idx": 0, "answers": [], "questions": questions, "guild_id": int(guild.id) if guild else 0}
        emb = build_application_dm_embed(self.settings, guild, questions)
        try:
            await user.send(embed=emb)
            await user.send(f"1/{len(questions)}: {questions[0]}")
        except Exception:
            pass
        return questions

    async def handle_dm_answer(self, message: discord.Message):
        if message.author.bot:
            return
        user_id = int(message.author.id)
        sess = self._sessions.get(user_id)
        if not sess:
            pending = self._followups.get(user_id) or []
            if not pending:
                return
            item = pending.pop(0)
            if not pending:
                self._followups.pop(user_id, None)
            self._mark_dm_handled(user_id)
            question = str(item.get("question") or "").strip()
            guild_id = int(item.get("guild_id") or 0)
            thread_id = int(item.get("thread_id") or 0)
            app_id = int(item.get("app_id") or 0)
            staff_id = int(item.get("staff_id") or 0)
            text = (message.content or "").strip()
            if not text:
                return
            guild = self.bot.get_guild(guild_id) if guild_id else None
            if not guild and guild_id:
                try:
                    guild = await self.bot.fetch_guild(guild_id)
                except Exception:
                    guild = None
            thread = None
            if guild and thread_id:
                thread = guild.get_thread(thread_id)
                if not thread:
                    try:
                        fetched = await self.bot.fetch_channel(thread_id)
                        thread = fetched if isinstance(fetched, discord.Thread) else None
                    except Exception:
                        thread = None
            if thread:
                emb = build_application_followup_answer_embed(self.settings, guild, message.author, question, text)
                view = ApplicationDecisionView(app_id=app_id) if app_id else None
                header = f"Rückfrage von <@{staff_id}> an {message.author.mention}" if staff_id else None
                try:
                    await thread.send(content=header, embed=emb, view=view)
                except Exception:
                    pass
            try:
                await message.author.send("✅ Danke! Deine Antwort wurde ans Team weitergeleitet.")
            except Exception:
                pass
            return
        text = (message.content or "").strip()
        if not text:
            return
        self._mark_dm_handled(user_id)
        sess["answers"].append(text)
        sess["idx"] += 1
        idx = int(sess["idx"])
        questions = sess["questions"]
        if idx >= len(questions):
            guild_id = int(sess.get("guild_id") or 0)
            guild = self.bot.get_guild(guild_id) if guild_id else None
            if not guild and guild_id:
                try:
                    guild = await self.bot.fetch_guild(guild_id)
                except Exception:
                    guild = None
            if guild:
                try:
                    interaction = _FakeInteraction(guild, message.author)
                    await self.start_application(interaction, sess["answers"])
                    await message.author.send("✅ Bewerbung wurde eingereicht. Danke!")
                except Exception:
                    await message.author.send("⚠️ Bewerbung konnte nicht eingereicht werden.")
            else:
                await message.author.send("⚠️ Server nicht gefunden. Bitte melde dich beim Team.")
            self._sessions.pop(int(message.author.id), None)
            return
        next_q = questions[idx]
        try:
            await message.author.send(f"{idx + 1}/{len(questions)}: {next_q}")
        except Exception:
            pass


    async def start_application(self, interaction: discord.Interaction, answers: list[str]):
        if not interaction.guild or not interaction.user:
            return False, "guild_only"

        cfg = self._config()
        enabled = bool(cfg.get("enabled", True))
        if not enabled:
            return False, "disabled"

        forum_id = int(cfg.get("forum_channel_id", 0) or 0)
        if not forum_id:
            return False, "forum_missing"

        guild = interaction.guild
        forum = guild.get_channel(forum_id)
        if not isinstance(forum, discord.ForumChannel):
            try:
                fetched = await self.bot.fetch_channel(int(forum_id))
                forum = fetched if isinstance(fetched, discord.ForumChannel) else None
            except Exception:
                forum = None
        if not isinstance(forum, discord.ForumChannel):
            return False, "forum_invalid"

        questions = self._questions()
        embed = build_application_embed(self.settings, guild, interaction.user, questions, answers)
        mention_role_id = int(cfg.get("ping_role_id", 0) or 0)
        mention = f"<@&{mention_role_id}>" if mention_role_id else ""
        title = f"Bewerbung von {interaction.user.display_name}"

        created = await forum.create_thread(name=title[:100], content=mention or None, embeds=[embed])
        thread = created.thread

        app_id = await self.db.create_application(guild.id, interaction.user.id, thread.id, questions, answers)
        if app_id:
            try:
                starter = getattr(created, "message", None)
                if starter:
                    await starter.edit(view=ApplicationDecisionView(app_id=int(app_id)))
            except Exception:
                pass
        await self.logger.emit(
            self.bot,
            "application_created",
            {"application_id": int(app_id), "user_id": int(interaction.user.id), "thread_id": int(thread.id)},
        )
        return True, None

    async def send_followup_question(self, interaction: discord.Interaction, user: discord.User, question: str):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False, "guild_only"
        if not is_staff(self.settings, interaction.user):
            return False, "no_perms"
        cfg = self._config()
        forum_id = int(cfg.get("forum_channel_id", 0) or 0)
        thread = interaction.channel if isinstance(interaction.channel, discord.Thread) else None
        parent = getattr(thread, "parent", None) if thread else None
        if not thread or not parent or int(getattr(parent, "id", 0)) != forum_id:
            return False, "thread_only"
        app = await self.db.get_application_by_thread(int(interaction.guild.id), int(thread.id))
        if not app:
            return False, "application_missing"
        app_id = int(app[0])
        app_user_id = int(app[1]) if app[1] is not None else 0
        if app_user_id and int(user.id) != app_user_id:
            return False, "user_mismatch"
        question_text = (question or "").strip()
        if not question_text:
            return False, "question_missing"
        emb = build_application_followup_dm_embed(self.settings, interaction.guild, interaction.user, question_text)
        try:
            await user.send(embed=emb)
        except Exception as e:
            return False, f"dm_failed:{type(e).__name__}"
        self._followups.setdefault(int(user.id), []).append(
            {
                "guild_id": int(interaction.guild.id),
                "thread_id": int(thread.id),
                "question": question_text,
                "staff_id": int(interaction.user.id),
                "app_id": app_id,
            }
        )
        try:
            await thread.send(f"💬 Rückfrage an {user.mention} gesendet.")
        except Exception:
            pass
        return True, None

    async def decide_application(self, interaction: discord.Interaction, app_id: int, accepted: bool):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return False, "guild_only"
        if not is_staff(self.settings, interaction.user):
            return False, "no_perms"
        row = await self.db.get_application(int(app_id))
        if not row:
            return False, "application_missing"
        guild_id = int(row[1]) if row[1] is not None else 0
        if guild_id and interaction.guild.id != guild_id:
            return False, "wrong_guild"
        status = str(row[4])
        if status in ("accepted", "denied"):
            return False, "already_decided"
        await self.db.set_application_status(int(app_id), "accepted" if accepted else "denied")
        user_id = int(row[2]) if row[2] is not None else 0
        thread_id = int(row[3]) if row[3] is not None else 0
        thread = interaction.guild.get_thread(thread_id) if thread_id else None
        try:
            emb = build_application_decision_embed(self.settings, interaction.guild, accepted, interaction.user)
            if thread:
                await thread.send(embed=emb)
        except Exception:
            pass
        if user_id:
            try:
                user = await self.bot.fetch_user(user_id)
                emb = build_application_decision_embed(self.settings, interaction.guild, accepted, interaction.user)
                await user.send(embed=emb)
            except Exception:
                pass
        return True, None


class _FakeInteraction:
    def __init__(self, guild: discord.Guild, user: discord.User):
        self.guild = guild
        self.user = user

    async def start_application(self, interaction: discord.Interaction, answers: list[str]):
        if not interaction.guild or not interaction.user:
            return False, "guild_only"

        cfg = self._config()
        enabled = bool(cfg.get("enabled", True))
        if not enabled:
            return False, "disabled"

        forum_id = int(cfg.get("forum_channel_id", 0) or 0)
        if not forum_id:
            return False, "forum_missing"

        guild = interaction.guild
        forum = guild.get_channel(forum_id)
        if not isinstance(forum, discord.ForumChannel):
            try:
                fetched = await self.bot.fetch_channel(int(forum_id))
                forum = fetched if isinstance(fetched, discord.ForumChannel) else None
            except Exception:
                forum = None
        if not isinstance(forum, discord.ForumChannel):
            return False, "forum_invalid"

        questions = self._questions()
        embed = build_application_embed(self.settings, guild, interaction.user, questions, answers)
        mention_role_id = int(cfg.get("ping_role_id", 0) or 0)
        mention = f"<@&{mention_role_id}>" if mention_role_id else ""
        title = f"📝 Bewerbung von {interaction.user.display_name}"

        created = await forum.create_thread(name=title[:100], content=mention or None, embeds=[embed])
        thread = created.thread

        app_id = await self.db.create_application(guild.id, interaction.user.id, thread.id, questions, answers)
        await self.logger.emit(
            self.bot,
            "application_created",
            {"application_id": int(app_id), "user_id": int(interaction.user.id), "thread_id": int(thread.id)},
        )
        return True, None

    async def send_dm_intro(self, user: discord.User, guild: discord.Guild | None):
        questions = self._questions()
        emb = build_application_dm_embed(self.settings, guild, questions)
        try:
            await user.send(embed=emb)
        except Exception:
            pass
        return questions

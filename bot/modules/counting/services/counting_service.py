from __future__ import annotations

import asyncio
import ast
import re
import math
import operator as op
import time
from dataclasses import dataclass

import discord

from bot.utils.emojis import em
from bot.modules.counting.formatting.counting_embeds import (
    build_counting_fail_embed,
    build_counting_milestone_embed,
    build_counting_record_embed,
)
from bot.modules.logs.formatting.log_embeds import build_bot_debug_embed


_ALLOWED_CHARS = re.compile(r"^[0-9A-Za-z_.,+\-*/%^=()\s]+$")
_ALLOWED_FUNCS: dict[str, object] = {
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "sqrt": math.sqrt,
    "pow": pow,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
}
_ALLOWED_CONSTS: dict[str, float] = {
    "pi": math.pi,
    "e": math.e,
}
_BIN_OPS: dict[type[ast.AST], object] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}
_UNARY_OPS: dict[type[ast.AST], object] = {
    ast.UAdd: op.pos,
    ast.USub: op.neg,
}


@dataclass
class CountingState:
    current_number: int = 1
    last_user_id: int | None = None
    highscore: int = 0
    total_counts: int = 0
    total_fails: int = 0
    last_count_value: int | None = None
    last_count_user_id: int | None = None
    last_count_at: str | None = None


class CountingService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._cache: dict[int, CountingState] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._cooldowns: dict[tuple[int, int], float] = {}
        self._channel_name_tasks: dict[int, asyncio.Task] = {}
        self._channel_name_pending: dict[int, dict[str, int]] = {}
        self._channel_name_versions: dict[int, int] = {}
        self._channel_topic_tasks: dict[int, asyncio.Task] = {}
        self._channel_topic_pending: dict[int, dict[str, int]] = {}
        self._channel_topic_versions: dict[int, int] = {}

    def _get_lock(self, channel_id: int) -> asyncio.Lock:
        lock = self._locks.get(channel_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[channel_id] = lock
        return lock

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "counting.enabled", True))

    def _channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "counting.channel_id", 0) or 0)

    def _allow_consecutive(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "counting.allow_consecutive", False))

    def _milestone_every(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "counting.milestone_every", 100) or 0)

    def _record_every(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "counting.record_every", 10) or 0)

    def _channel_name_enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "counting.channel_name_enabled", True))

    def _channel_name_template(self, guild_id: int) -> str:
        return str(self.settings.get_guild(guild_id, "counting.channel_name_template", "counting-{count}") or "")

    def _channel_name_channel_id(self, guild_id: int, fallback: int) -> int:
        cid = int(self.settings.get_guild_int(guild_id, "counting.channel_name_channel_id", 0) or 0)
        return cid if cid else fallback

    def _count_timeout_seconds(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "counting.timeout_seconds", 0) or 0)

    def _debug_enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "counting.debug", True))

    def _render_template(self, template: str, values: dict[str, int | str]) -> str:
        out = str(template or "")
        for key, val in values.items():
            out = out.replace("{" + key + "}", str(val))
        return out.strip()

    def _build_channel_topic(self, state: CountingState) -> str:
        last_count = int(state.last_count_value) if state.last_count_value is not None else max(0, int(state.current_number) - 1)
        streak = max(0, int(state.current_number) - 1)
        total_msgs = int(state.total_counts) + int(state.total_fails)
        topic = (
            f"🔢 Letzter Count: {last_count} | "
            f"🔁 Streak: {streak} | "
            f"💬 Gesamt: {total_msgs}"
        )
        return topic.strip()

    async def _emit_debug(self, guild: discord.Guild | None, title: str, payload: dict | None = None):
        if not guild or not self._debug_enabled(guild.id):
            return
        logs = getattr(self.bot, "forum_logs", None)
        if not logs:
            return
        try:
            emb = build_bot_debug_embed(self.settings, guild, title, payload or {})
            await logs.emit(guild, "bot_errors", emb)
        except Exception:
            pass

    def _is_candidate_expression(self, content: str) -> bool:
        if not content:
            return False
        return any(ch.isdigit() for ch in content)

    def _extract_single_int(self, content: str) -> int | None:
        nums = re.findall(r"\d+", content)
        if len(nums) != 1:
            return None
        try:
            value = int(nums[0])
        except Exception:
            return None
        if value < 0:
            return None
        return value

    def _eval_ast(self, node: ast.AST) -> int | None:
        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body)

        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value

        if isinstance(node, ast.Name):
            return _ALLOWED_CONSTS.get(node.id)

        if isinstance(node, ast.UnaryOp):
            fn = _UNARY_OPS.get(type(node.op))
            if not fn:
                return None
            val = self._eval_ast(node.operand)
            if val is None:
                return None
            return fn(val)

        if isinstance(node, ast.BinOp):
            fn = _BIN_OPS.get(type(node.op))
            if not fn:
                return None
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
                return None
            return fn(left, right)

        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                return None
            fn = _ALLOWED_FUNCS.get(node.func.id)
            if not fn or node.keywords:
                return None
            args = [self._eval_ast(arg) for arg in node.args]
            if any(arg is None for arg in args):
                return None
            try:
                return fn(*args)
            except Exception:
                return None

        return None

    def evaluate_expression(self, content: str) -> int | None:
        try:
            expr = content.replace(" ", "").replace("^", "**").replace(",", ".")
            parts = [p for p in expr.split("=") if p != ""]
            if not parts:
                return None
            values: list[int] = []
            for part in parts:
                node = ast.parse(part, mode="eval")
                value = self._eval_ast(node)
                if value is None or isinstance(value, bool) or not isinstance(value, (int, float)):
                    return None
                if not math.isfinite(value):
                    return None
                rounded = int(round(value))
                if abs(value - rounded) > 1e-9 or rounded < 0:
                    return None
                values.append(rounded)
            if not values:
                return None
            if len(set(values)) != 1:
                return None
            return values[0]
        except Exception:
            return None

    async def _send_notice(self, message: discord.Message, text: str, delete_after: int = 6):
        try:
            notice = await message.reply(text, mention_author=False)
        except Exception:
            return
        if delete_after and delete_after > 0:
            async def _cleanup(msg: discord.Message):
                try:
                    await asyncio.sleep(delete_after)
                    await msg.delete()
                except Exception:
                    pass

            asyncio.create_task(_cleanup(notice))

    async def get_state(self, channel_id: int, guild_id: int) -> CountingState:
        cached = self._cache.get(channel_id)
        if cached:
            return cached
        row = None
        try:
            row = await self.db.get_counting_state(guild_id, channel_id)
        except Exception:
            row = None
        if row:
            state = CountingState(
                current_number=int(row[2] or 1),
                last_user_id=int(row[3]) if row[3] is not None else None,
                highscore=int(row[4] or 0),
                total_counts=int(row[5] or 0),
                total_fails=int(row[6] or 0),
                last_count_value=int(row[8]) if len(row) > 8 and row[8] is not None else None,
                last_count_user_id=int(row[9]) if len(row) > 9 and row[9] is not None else None,
                last_count_at=str(row[10]) if len(row) > 10 and row[10] is not None else None,
            )
            if state.last_count_value is None and int(state.current_number) > 1:
                state.last_count_value = int(state.current_number) - 1
                try:
                    await self.save_state(channel_id, guild_id, state)
                except Exception:
                    pass
        else:
            state = CountingState()
        self._cache[channel_id] = state
        return state

    async def save_state(self, channel_id: int, guild_id: int, state: CountingState):
        self._cache[channel_id] = state
        try:
            await self.db.upsert_counting_state(
                guild_id=guild_id,
                channel_id=channel_id,
                current_number=state.current_number,
                last_user_id=state.last_user_id,
                highscore=state.highscore,
                total_counts=state.total_counts,
                total_fails=state.total_fails,
                last_count_value=state.last_count_value,
                last_count_user_id=state.last_count_user_id,
                last_count_at=state.last_count_at,
            )
        except Exception:
            pass

    async def reset_state(self, channel_id: int, guild_id: int, full: bool = False) -> CountingState:
        state = await self.get_state(channel_id, guild_id)
        state.current_number = 1
        state.last_user_id = None
        if full:
            state.highscore = 0
            state.total_counts = 0
            state.total_fails = 0
            state.last_count_value = None
            state.last_count_user_id = None
            state.last_count_at = None
        await self.save_state(channel_id, guild_id, state)
        return state

    def _apply_reset(self, state: CountingState) -> int:
        last_count = max(0, int(state.current_number) - 1)
        if last_count > int(state.highscore):
            state.highscore = int(last_count)
        state.current_number = 1
        state.last_user_id = None
        return last_count

    async def _update_channel_name(
        self,
        guild: discord.Guild,
        channel_id: int,
        state: CountingState,
        last_value: int | None = None,
    ):
        if not self._channel_name_enabled(guild.id):
            return
        template = self._channel_name_template(guild.id)
        if not template:
            return
        target_id = self._channel_name_channel_id(guild.id, channel_id)
        ch = guild.get_channel(int(target_id))
        if not isinstance(ch, discord.abc.GuildChannel):
            try:
                ch = await guild.fetch_channel(int(target_id))
            except Exception as err:
                await self._emit_debug(
                    guild,
                    "counting_channel_fetch_failed",
                    {
                        "channel_id": int(channel_id),
                        "target_id": int(target_id),
                        "error": type(err).__name__,
                    },
                )
                return
        if not isinstance(ch, discord.abc.GuildChannel):
            await self._emit_debug(
                guild,
                "counting_channel_not_found",
                {
                    "channel_id": int(channel_id),
                    "target_id": int(target_id),
                },
            )
            return

        count_val = last_value if last_value is not None else max(0, state.current_number - 1)
        await self._update_channel_name_values(
            guild,
            channel_id,
            template,
            count_val=int(count_val),
            next_val=int(state.current_number),
            highscore=int(state.highscore),
        )

    async def _update_channel_name_values(
        self,
        guild: discord.Guild,
        channel_id: int,
        template: str,
        count_val: int,
        next_val: int,
        highscore: int,
    ):
        if not template:
            return
        target_id = self._channel_name_channel_id(guild.id, channel_id)
        ch = guild.get_channel(int(target_id))
        if not isinstance(ch, discord.abc.GuildChannel):
            return

        rendered = self._render_template(
            template,
            {
                "count": int(count_val),
                "next": int(next_val),
                "highscore": int(highscore),
            },
        )
        if not rendered:
            return
        rendered = rendered[:90]
        if ch.name != rendered:
            try:
                await ch.edit(name=rendered, reason="Counting update")
            except discord.Forbidden as err:
                await self._emit_debug(
                    guild,
                    "counting_channel_rename_forbidden",
                    {
                        "channel_id": int(channel_id),
                        "target_id": int(target_id),
                        "error": type(err).__name__,
                    },
                )
            except discord.HTTPException as err:
                await self._emit_debug(
                    guild,
                    "counting_channel_rename_http",
                    {
                        "channel_id": int(channel_id),
                        "target_id": int(target_id),
                        "error": type(err).__name__,
                        "status": getattr(err, "status", None),
                    },
                )
            except Exception as err:
                await self._emit_debug(
                    guild,
                    "counting_channel_rename_error",
                    {
                        "channel_id": int(channel_id),
                        "target_id": int(target_id),
                        "error": type(err).__name__,
                    },
                )

    def _schedule_channel_name_update(
        self,
        guild: discord.Guild,
        channel_id: int,
        state: CountingState,
        last_value: int | None = None,
    ):
        if not self._channel_name_enabled(guild.id):
            return
        template = self._channel_name_template(guild.id)
        if not template:
            return

        count_val = int(last_value) if last_value is not None else max(0, int(state.current_number) - 1)
        payload = {
            "count": int(count_val),
            "next": int(state.current_number),
            "highscore": int(state.highscore),
        }
        self._channel_name_pending[int(channel_id)] = payload
        self._channel_name_versions[int(channel_id)] = int(self._channel_name_versions.get(int(channel_id), 0)) + 1

        existing = self._channel_name_tasks.get(int(channel_id))
        if existing and not existing.done():
            return

        async def _runner():
            try:
                while True:
                    version = int(self._channel_name_versions.get(int(channel_id), 0))
                    await asyncio.sleep(0.4)
                    data = self._channel_name_pending.get(int(channel_id))
                    if not data:
                        return
                    await self._update_channel_name_values(
                        guild,
                        channel_id,
                        template,
                        count_val=data["count"],
                        next_val=data["next"],
                        highscore=data["highscore"],
                    )
                    if int(self._channel_name_versions.get(int(channel_id), 0)) == version:
                        return
            finally:
                self._channel_name_tasks.pop(int(channel_id), None)

        self._channel_name_tasks[int(channel_id)] = asyncio.create_task(_runner())

    def _schedule_channel_topic_update(
        self,
        guild: discord.Guild,
        channel_id: int,
        state: CountingState,
    ):
        payload = {
            "current_number": int(state.current_number),
            "last_count_value": int(state.last_count_value) if state.last_count_value is not None else None,
            "counts": int(state.total_counts),
            "fails": int(state.total_fails),
        }
        self._channel_topic_pending[int(channel_id)] = payload
        self._channel_topic_versions[int(channel_id)] = int(self._channel_topic_versions.get(int(channel_id), 0)) + 1

        existing = self._channel_topic_tasks.get(int(channel_id))
        if existing and not existing.done():
            return

        async def _runner():
            try:
                while True:
                    version = int(self._channel_topic_versions.get(int(channel_id), 0))
                    await asyncio.sleep(0.6)
                    data = self._channel_topic_pending.get(int(channel_id))
                    if not data:
                        return
                    ch = guild.get_channel(int(channel_id))
                    if not ch or not hasattr(ch, "topic"):
                        try:
                            ch = await guild.fetch_channel(int(channel_id))
                        except Exception as err:
                            await self._emit_debug(
                                guild,
                                "counting_topic_channel_fetch_failed",
                                {
                                    "channel_id": int(channel_id),
                                    "error": type(err).__name__,
                                },
                            )
                            return
                    if not ch or not hasattr(ch, "topic"):
                        await self._emit_debug(
                            guild,
                            "counting_topic_channel_invalid",
                            {
                                "channel_id": int(channel_id),
                                "type": str(getattr(ch, "type", None)),
                            },
                        )
                        return
                    last_count_value = data.get("last_count_value")
                    current_number = int(data.get("current_number") or 1)
                    last_count = int(last_count_value) if last_count_value is not None else max(0, current_number - 1)
                    streak = max(0, current_number - 1)
                    total_msgs = int(data["counts"]) + int(data["fails"])
                    rendered = (
                        f"🔢 • Letzter Count: {last_count} | "
                        f"🔁 • Streak: {streak} | "
                        f"💬 • Gesamt: {total_msgs}"
                    ).strip()
                    rendered = rendered[:900]
                    if getattr(ch, "topic", None) != rendered:
                        try:
                            await ch.edit(topic=rendered, reason="Counting topic update")
                        except discord.Forbidden as err:
                            await self._emit_debug(
                                guild,
                                "counting_topic_forbidden",
                                {
                                    "channel_id": int(channel_id),
                                    "error": type(err).__name__,
                                },
                            )
                        except discord.HTTPException as err:
                            await self._emit_debug(
                                guild,
                                "counting_topic_http",
                                {
                                    "channel_id": int(channel_id),
                                    "error": type(err).__name__,
                                    "status": getattr(err, "status", None),
                                },
                            )
                        except Exception as err:
                            await self._emit_debug(
                                guild,
                                "counting_topic_error",
                                {
                                    "channel_id": int(channel_id),
                                    "error": type(err).__name__,
                                },
                            )
                    if int(self._channel_topic_versions.get(int(channel_id), 0)) == version:
                        return
            finally:
                self._channel_topic_tasks.pop(int(channel_id), None)

        self._channel_topic_tasks[int(channel_id)] = asyncio.create_task(_runner())

    async def sync_guild(self, guild: discord.Guild):
        if not guild or not self._enabled(guild.id):
            return
        channel_id = self._channel_id(guild.id)
        if not channel_id:
            return
        state = await self.get_state(channel_id, guild.id)
        self._schedule_channel_name_update(guild, channel_id, state)
        self._schedule_channel_topic_update(guild, channel_id, state)

    async def handle_message(self, message: discord.Message):
        if not message.guild:
            return
        if message.author.bot:
            return
        guild_id = int(message.guild.id)
        if not self._enabled(guild_id):
            return
        channel_id = self._channel_id(guild_id)
        if not channel_id or int(message.channel.id) != channel_id:
            return
        content = str(message.content or "").strip()
        if not self._is_candidate_expression(content):
            return

        lock = self._get_lock(channel_id)
        action = None
        remaining = None
        value = None
        prev_highscore = None
        state = None
        fail_reason = None
        expected = None
        got = None

        async with lock:
            timeout_seconds = self._count_timeout_seconds(guild_id)
            if timeout_seconds > 0:
                key = (channel_id, int(message.author.id))
                last_ts = self._cooldowns.get(key)
                if last_ts is not None:
                    remaining = timeout_seconds - (time.monotonic() - last_ts)
                    if remaining > 0:
                        action = "cooldown"
            if action:
                pass
            else:
                state = await self.get_state(channel_id, guild_id)

            if action:
                pass
            elif not self._allow_consecutive(guild_id):
                if state.last_user_id and int(state.last_user_id) == int(message.author.id):
                    action = "consecutive"

            if action:
                pass
            else:
                value = self.evaluate_expression(content)
                if value is None:
                    value = self._extract_single_int(content)

            if action:
                pass
            elif value is None:
                fail_reason = "Ungültige Rechnung – nur Scheiße gesendet."
                expected = state.current_number
                got = None
                await self._apply_fail_state(channel_id, guild_id, state)
                action = "fail"
            elif int(value) != int(state.current_number):
                fail_reason = "Falsch gezählt."
                expected = state.current_number
                got = value
                await self._apply_fail_state(channel_id, guild_id, state)
                action = "fail"
            else:
                prev_highscore = int(state.highscore)
                state.total_counts += 1
                state.last_user_id = int(message.author.id)
                if value > state.highscore:
                    state.highscore = int(value)
                state.current_number = int(value) + 1
                state.last_count_value = int(value)
                state.last_count_user_id = int(message.author.id)
                try:
                    state.last_count_at = await self.db.now_iso()
                except Exception:
                    pass

                await self.save_state(channel_id, guild_id, state)
                self._cooldowns[(channel_id, int(message.author.id))] = time.monotonic()
                action = "success"

        if action == "cooldown":
            try:
                await message.delete()
            except Exception:
                pass
            await self._send_notice(
                message,
                f"⏳ Warte bitte noch **{int(math.ceil(remaining))}s** bevor du wieder zählen darfst.",
            )
            return

        if action == "consecutive":
            try:
                await message.delete()
            except Exception:
                pass
            await self._send_notice(
                message,
                "🚫 Du darfst nicht zweimal hintereinander zählen.",
            )
            return

        if action == "fail":
            await self._notify_fail(
                message,
                state,
                reason=fail_reason or "Falsch gezählt.",
                expected=expected,
                got=got,
            )
            return

        if action != "success":
            return

        try:
            await message.add_reaction(em(self.settings, "green", message.guild) or "✅")
        except Exception:
            pass

        self._schedule_channel_name_update(message.guild, channel_id, state, last_value=value)
        self._schedule_channel_topic_update(message.guild, channel_id, state)

        if self._milestone_every(guild_id) > 0 and value % self._milestone_every(guild_id) == 0:
            view = build_counting_milestone_embed(
                self.settings,
                message.guild,
                milestone=value,
                highscore=state.highscore,
                total_counts=state.total_counts,
                total_fails=state.total_fails,
            )
            await message.channel.send(view=view)
        elif (
            self._record_every(guild_id) > 0
            and value > prev_highscore
            and prev_highscore > 0
            and value % self._record_every(guild_id) == 0
        ):
            view = build_counting_record_embed(self.settings, message.guild, value, state.highscore)
            await message.channel.send(view=view)

        return

    async def _apply_fail_state(
        self,
        channel_id: int,
        guild_id: int,
        state: CountingState,
    ):
        state.total_fails += 1
        self._apply_reset(state)
        await self.save_state(channel_id, guild_id, state)

    async def _notify_fail(
        self,
        message: discord.Message,
        state: CountingState,
        reason: str,
        expected: int | None,
        got: int | None,
    ):
        view = build_counting_fail_embed(
            self.settings,
            message.guild,
            reason=reason,
            expected=expected,
            got=got,
            highscore=state.highscore,
            total_fails=state.total_fails,
            reset_to=state.current_number,
        )
        try:
            await message.reply(view=view, mention_author=False)
        except Exception:
            try:
                exp = str(expected) if expected is not None else "—"
                got_val = str(got) if got is not None else "—"
                await message.channel.send(
                    f"🚫 **Counting-Fehler**: {reason}\n"
                    f"Erwartet: {exp} · Gesendet: {got_val} · Reset: {state.current_number}"
                )
            except Exception:
                pass
        try:
            await message.add_reaction(em(self.settings, "red", message.guild) or "❌")
        except Exception:
            pass

        self._schedule_channel_name_update(message.guild, int(message.channel.id), state)
        self._schedule_channel_topic_update(message.guild, int(message.channel.id), state)

    async def _handle_fail(
        self,
        message: discord.Message,
        state: CountingState,
        guild_id: int,
        reason: str,
        expected: int | None,
        got: int | None,
    ):
        await self._apply_fail_state(int(message.channel.id), guild_id, state)
        await self._notify_fail(message, state, reason=reason, expected=expected, got=got)

from __future__ import annotations

import asyncio
import ast
import re
from dataclasses import dataclass

import discord

from bot.modules.counting.formatting.counting_embeds import (
    build_counting_fail_embed,
    build_counting_milestone_embed,
    build_counting_record_embed,
)


_ALLOWED_CHARS = re.compile(r"^[0-9+\-*/\s()]+$")


@dataclass
class CountingState:
    current_number: int = 1
    last_user_id: int | None = None
    highscore: int = 0
    total_counts: int = 0
    total_fails: int = 0


class CountingService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._cache: dict[int, CountingState] = {}
        self._locks: dict[int, asyncio.Lock] = {}

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

    def _render_template(self, template: str, values: dict[str, int | str]) -> str:
        out = str(template or "")
        for key, val in values.items():
            out = out.replace("{" + key + "}", str(val))
        return out.strip()

    def _is_candidate_expression(self, content: str) -> bool:
        if not content:
            return False
        if not _ALLOWED_CHARS.match(content):
            return False
        return any(ch.isdigit() for ch in content)

    def _eval_ast(self, node: ast.AST) -> int | None:
        if isinstance(node, ast.Expression):
            return self._eval_ast(node.body)

        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.UAdd):
                return self._eval_ast(node.operand)
            return None

        if isinstance(node, ast.BinOp):
            left = self._eval_ast(node.left)
            right = self._eval_ast(node.right)
            if left is None or right is None:
                return None
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                if right == 0:
                    return None
                return left // right
            return None

        return None

    def evaluate_expression(self, content: str) -> int | None:
        try:
            expr = content.replace(" ", "")
            node = ast.parse(expr, mode="eval")
            value = self._eval_ast(node)
            if value is None:
                return None
            if not isinstance(value, int):
                return None
            if value < 0:
                return None
            return value
        except Exception:
            return None

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
            )
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
            )
        except Exception:
            pass

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
            return

        count_val = last_value if last_value is not None else max(0, state.current_number - 1)
        rendered = self._render_template(
            template,
            {
                "count": int(count_val),
                "next": int(state.current_number),
                "highscore": int(state.highscore),
            },
        )
        if not rendered:
            return
        rendered = rendered[:90]
        if ch.name != rendered:
            try:
                await ch.edit(name=rendered, reason="Counting update")
            except Exception:
                pass

    async def sync_guild(self, guild: discord.Guild):
        if not guild or not self._enabled(guild.id):
            return
        channel_id = self._channel_id(guild.id)
        if not channel_id:
            return
        state = await self.get_state(channel_id, guild.id)
        await self._update_channel_name(guild, channel_id, state)

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
        async with lock:
            state = await self.get_state(channel_id, guild_id)

            if not self._allow_consecutive(guild_id):
                if state.last_user_id and int(state.last_user_id) == int(message.author.id):
                    await self._handle_fail(
                        message,
                        state,
                        guild_id,
                        reason="Du darfst nicht zweimal hintereinander zaehlen!",
                        expected=state.current_number,
                        got=None,
                    )
                    return

            value = self.evaluate_expression(content)
            if value is None:
                await self._handle_fail(
                    message,
                    state,
                    guild_id,
                    reason="Ungueltige Rechnung.",
                    expected=state.current_number,
                    got=None,
                )
                return

            if int(value) != int(state.current_number):
                await self._handle_fail(
                    message,
                    state,
                    guild_id,
                    reason="Falsch gezaehlt.",
                    expected=state.current_number,
                    got=value,
                )
                return

            prev_highscore = int(state.highscore)
            state.total_counts += 1
            state.last_user_id = int(message.author.id)
            if value > state.highscore:
                state.highscore = int(value)
            state.current_number = int(value) + 1

            await self.save_state(channel_id, guild_id, state)

            try:
                await message.add_reaction("?")
            except Exception:
                pass

            await self._update_channel_name(message.guild, channel_id, state, last_value=value)

            if self._milestone_every(guild_id) > 0 and value % self._milestone_every(guild_id) == 0:
                emb = build_counting_milestone_embed(
                    self.settings,
                    message.guild,
                    milestone=value,
                    highscore=state.highscore,
                    total_counts=state.total_counts,
                    total_fails=state.total_fails,
                )
                await message.channel.send(embed=emb)
            elif (
                self._record_every(guild_id) > 0
                and value > prev_highscore
                and prev_highscore > 0
                and value % self._record_every(guild_id) == 0
            ):
                emb = build_counting_record_embed(self.settings, message.guild, value, state.highscore)
                await message.channel.send(embed=emb)

    async def _handle_fail(
        self,
        message: discord.Message,
        state: CountingState,
        guild_id: int,
        reason: str,
        expected: int | None,
        got: int | None,
    ):
        state.total_fails += 1
        self._apply_reset(state)
        await self.save_state(int(message.channel.id), guild_id, state)

        emb = build_counting_fail_embed(
            self.settings,
            message.guild,
            reason=reason,
            expected=expected,
            got=got,
            highscore=state.highscore,
            reset_to=state.current_number,
        )
        try:
            await message.reply(embed=emb, mention_author=False)
        except Exception:
            pass
        try:
            await message.add_reaction("?")
        except Exception:
            pass

        await self._update_channel_name(message.guild, int(message.channel.id), state)

        return

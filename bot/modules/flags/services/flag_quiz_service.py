from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import asyncio
import random
import re
import math
from difflib import SequenceMatcher
from typing import Any

import discord
import httpx

from bot.modules.flags.formatting.flag_embeds import (
    build_dashboard_view,
    build_round_embed,
    build_result_embed,
)


@dataclass
class ActiveRound:
    guild_id: int
    channel_id: int
    user_id: int
    mode: str
    code: str
    flag_url: str
    answer_names: set[str]
    button_map: dict[str, str]
    prompt_message_id: int
    task: asyncio.Task | None
    end_at: datetime
    wager_points: int = 0


class FlagQuizService:
    TIME_LIMIT_SECONDS = 30
    TIME_LIMIT_BET_SECONDS = 15
    POINTS_NORMAL = 15
    POINTS_EASY = 3
    POINTS_DAILY = 25
    STREAK_ACHIEVEMENTS = [5, 10, 25, 50]
    DEFAULT_BLACKLIST_CODES = {"AQ", "BV", "HM", "TF", "UM"}

    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._rounds: dict[tuple[int, int, int], ActiveRound] = {}
        self._codes: list[str] = ["DE", "US", "GB", "FR", "IT", "ES", "NL", "PL", "SE", "NO", "JP", "KR", "CN", "BR", "AR", "MX", "CA", "AU", "AT", "CH"]
        self._code_to_name: dict[str, str] = {}
        self._code_to_flag_url: dict[str, str] = {}
        self._alias_to_code: dict[str, str] = {
            "deutschland": "DE",
            "germany": "DE",
            "usa": "US",
            "united states": "US",
            "vereinigte staaten": "US",
            "uk": "GB",
            "united kingdom": "GB",
            "great britain": "GB",
            "grossbritannien": "GB",
            "frankreich": "FR",
            "france": "FR",
            "italien": "IT",
            "italy": "IT",
            "spanien": "ES",
            "spain": "ES",
            "japan": "JP",
            "suedkorea": "KR",
            "südkorea": "KR",
            "south korea": "KR",
            "china": "CN",
            "brasilien": "BR",
            "brazil": "BR",
            "argentinien": "AR",
            "argentina": "AR",
            "kanada": "CA",
            "canada": "CA",
            "australien": "AU",
            "austria": "AT",
            "oesterreich": "AT",
            "österreich": "AT",
            "schweiz": "CH",
            "switzerland": "CH",
        }
        self._loaded_country_data = False
        self._last_round_start_at: dict[tuple[int, int, int], datetime] = {}
        self._recent_codes_by_guild: dict[int, list[str]] = {}
        self._resolve_locks: dict[tuple[int, int, int], asyncio.Lock] = {}

    def _period_keys(self, now: datetime | None = None) -> tuple[str, str]:
        stamp = now or datetime.now(timezone.utc)
        iso = stamp.isocalendar()
        week_key = f"{int(iso.year):04d}-W{int(iso.week):02d}"
        month_key = f"{int(stamp.year):04d}-{int(stamp.month):02d}"
        return week_key, month_key

    def current_period_keys(self) -> tuple[str, str]:
        return self._period_keys()

    def _apply_period_rollover(self, stats: dict[str, Any], now: datetime | None = None):
        week_key, month_key = self._period_keys(now)
        if str(stats.get("weekly_key") or "") != week_key:
            stats["weekly_key"] = week_key
            stats["weekly_points"] = 0
        if str(stats.get("monthly_key") or "") != month_key:
            stats["monthly_key"] = month_key
            stats["monthly_points"] = 0

    def _enabled(self, guild_id: int) -> bool:
        try:
            return bool(self.settings.get_guild_bool(int(guild_id), "flags.enabled", True))
        except Exception:
            return True

    def _normalize(self, text: str) -> str:
        x = str(text or "").strip().lower()
        x = (
            x.replace("ä", "ae")
            .replace("ö", "oe")
            .replace("ü", "ue")
            .replace("ß", "ss")
        )
        x = re.sub(r"[^a-z0-9 ]", " ", x)
        x = re.sub(r"\s+", " ", x).strip()
        return x

    def _code_from_flag_emoji(self, text: str) -> str | None:
        chars = [ord(ch) for ch in str(text or "").strip() if 0x1F1E6 <= ord(ch) <= 0x1F1FF]
        if len(chars) < 2:
            return None
        a, b = chars[0], chars[1]
        return chr((a - 0x1F1E6) + ord("A")) + chr((b - 0x1F1E6) + ord("A"))

    def _is_fuzzy_match(self, guess: str, candidate: str) -> bool:
        g = self._normalize(guess)
        c = self._normalize(candidate)
        if not g or not c:
            return False
        if g == c:
            return True
        if abs(len(g) - len(c)) > 2:
            return False
        ratio = SequenceMatcher(None, g, c).ratio()
        if len(c) <= 5:
            return ratio >= 0.78
        return ratio >= 0.74

    async def _ensure_country_data(self):
        if self._loaded_country_data:
            return
        self._loaded_country_data = True
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.get("https://restcountries.com/v3.1/all?fields=cca2,name,translations,flags")
            if res.status_code != 200:
                return
            data = res.json()
            codes: list[str] = []
            for row in data:
                code = str((row or {}).get("cca2", "")).upper().strip()
                if len(code) != 2:
                    continue
                name = str(((row or {}).get("name", {}) or {}).get("common", code)).strip() or code
                de = str((((row or {}).get("translations", {}) or {}).get("deu", {}) or {}).get("common", "")).strip()
                # Für UI/Buttons bevorzugen wir den deutschen Ländernamen.
                self._code_to_name[code] = de or name
                flags = (row or {}).get("flags", {}) or {}
                flag_url = str(flags.get("png") or "").strip()
                if flag_url:
                    self._code_to_flag_url[code] = flag_url
                self._alias_to_code[self._normalize(name)] = code
                if de:
                    self._alias_to_code[self._normalize(de)] = code
                codes.append(code)
            if codes:
                self._codes = sorted(set(codes))
        except Exception:
            pass

    async def _guild_state(self, guild_id: int) -> dict[str, int]:
        row = await self.db.get_flag_quiz_guild(int(guild_id))
        return {
            "channel_id": int(row[1]) if row and row[1] else 0,
            "dashboard_message_id": int(row[2]) if row and row[2] else 0,
        }

    async def _get_player_stats(self, guild_id: int, user_id: int) -> dict[str, Any]:
        row = await self.db.get_flag_player_stats(int(guild_id), int(user_id))
        week_key, month_key = self._period_keys()
        if not row:
            return {
                "total_points": 0,
                "weekly_points": 0,
                "weekly_key": week_key,
                "monthly_points": 0,
                "monthly_key": month_key,
                "correct": 0,
                "wrong": 0,
                "current_streak": 0,
                "best_streak": 0,
                "last_daily": None,
            }
        stats = {
            "total_points": int(row[2] or 0),
            "weekly_points": int(row[3] or 0),
            "weekly_key": str(row[4] or ""),
            "monthly_points": int(row[5] or 0),
            "monthly_key": str(row[6] or ""),
            "correct": int(row[7] or 0),
            "wrong": int(row[8] or 0),
            "current_streak": int(row[9] or 0),
            "best_streak": int(row[10] or 0),
            "last_daily": str(row[11]) if row[11] else None,
        }
        self._apply_period_rollover(stats)
        return stats

    async def _save_player_stats(self, guild_id: int, user_id: int, stats: dict[str, Any]):
        await self.db.upsert_flag_player_stats(
            int(guild_id),
            int(user_id),
            int(stats["total_points"]),
            int(stats["weekly_points"]),
            str(stats.get("weekly_key") or ""),
            int(stats["monthly_points"]),
            str(stats.get("monthly_key") or ""),
            int(stats["correct"]),
            int(stats["wrong"]),
            int(stats["current_streak"]),
            int(stats["best_streak"]),
            stats.get("last_daily"),
        )

    async def _get_flag_stats(self, guild_id: int, code: str) -> dict[str, int]:
        row = await self.db.get_flag_stats(int(guild_id), str(code).upper())
        if not row:
            return {"asked": 0, "correct": 0, "wrong": 0}
        return {"asked": int(row[2] or 0), "correct": int(row[3] or 0), "wrong": int(row[4] or 0)}

    async def _save_flag_stats(self, guild_id: int, code: str, stats: dict[str, int]):
        await self.db.upsert_flag_stats(int(guild_id), str(code).upper(), int(stats["asked"]), int(stats["correct"]), int(stats["wrong"]))

    def _quiz_key(self, guild_id: int, channel_id: int, user_id: int) -> tuple[int, int, int]:
        return int(guild_id), int(channel_id), int(user_id)

    def _points_for_mode(self, guild_id: int, mode: str) -> int:
        mode_key = str(mode).lower()
        if mode_key == "easy":
            return max(1, int(self.settings.get_guild_int(guild_id, "flags.points.easy", self.POINTS_EASY)))
        if mode_key == "daily":
            return max(1, int(self.settings.get_guild_int(guild_id, "flags.points.daily", self.POINTS_DAILY)))
        return max(1, int(self.settings.get_guild_int(guild_id, "flags.points.normal", self.POINTS_NORMAL)))

    def _max_gain_per_round(self, guild_id: int) -> int:
        return max(1, int(self.settings.get_guild_int(guild_id, "flags.points.max_gain_per_round", 100)))

    def _max_wager_points(self, guild_id: int) -> int:
        return max(1, int(self.settings.get_guild_int(guild_id, "flags.bet.max_wager_points", 50)))

    def _start_cooldown_seconds(self, guild_id: int) -> int:
        return max(0, int(self.settings.get_guild_int(guild_id, "flags.round_cooldown_seconds", 5)))

    def _repeat_memory_size(self, guild_id: int) -> int:
        return max(0, int(self.settings.get_guild_int(guild_id, "flags.repeat_protection.last_n", 15)))

    async def _blacklisted_codes(self, guild_id: int) -> set[str]:
        await self._ensure_country_data()
        raw = self.settings.get_guild(guild_id, "flags.blacklist", [])
        blocked: set[str] = set(self.DEFAULT_BLACKLIST_CODES)
        if not isinstance(raw, list):
            return blocked
        for item in raw:
            probe = str(item or "").strip()
            if not probe:
                continue
            up = probe.upper()
            if len(up) == 2 and up in self._codes:
                blocked.add(up)
                continue
            resolved = await self._resolve_code(probe)
            if resolved:
                blocked.add(str(resolved).upper())
        return blocked

    async def _available_codes(self, guild_id: int) -> list[str]:
        blocked = await self._blacklisted_codes(guild_id)
        out = [c for c in self._codes if c not in blocked]
        return out if out else list(self._codes)

    def _remember_recent_code(self, guild_id: int, code: str):
        gid = int(guild_id)
        size = self._repeat_memory_size(gid)
        if size <= 0:
            return
        buf = self._recent_codes_by_guild.get(gid, [])
        buf.append(str(code).upper())
        if len(buf) > size:
            buf = buf[-size:]
        self._recent_codes_by_guild[gid] = buf

    async def _random_code(self, guild_id: int) -> str:
        pool = await self._available_codes(guild_id)
        if len(pool) <= 1:
            return pool[0]
        recent = set(self._recent_codes_by_guild.get(int(guild_id), []))
        filtered = [c for c in pool if c not in recent]
        base = filtered if filtered else pool
        return random.choice(base)

    async def _daily_code(self, guild_id: int) -> str:
        pool = await self._available_codes(guild_id)
        if not pool:
            pool = list(self._codes)
        today = datetime.now(timezone.utc).date().isoformat()
        idx = abs(hash((int(guild_id), today))) % max(1, len(pool))
        return pool[idx]

    async def _resolve_code(self, query: str) -> str | None:
        await self._ensure_country_data()
        norm = self._normalize(query)
        if len(norm) == 2:
            up = norm.upper()
            if up in self._codes:
                return up
        return self._alias_to_code.get(norm)

    def _name_for(self, code: str) -> str:
        return self._code_to_name.get(str(code).upper(), str(code).upper())

    def _flag_url_for(self, code: str) -> str:
        c = str(code or "").upper()
        direct = str(self._code_to_flag_url.get(c) or "").strip()
        if direct:
            return direct
        return f"https://flagcdn.com/h240/{c.lower()}.png"

    def _answer_candidates_for(self, code: str, name: str) -> set[str]:
        target = str(code).upper()
        out = {self._normalize(target), self._normalize(name)}
        for alias, mapped in self._alias_to_code.items():
            if str(mapped).upper() == target:
                out.add(self._normalize(alias))
        return {x for x in out if x}

    async def _dashboard_stats(self, guild: discord.Guild) -> dict[str, Any]:
        week_key, month_key = self._period_keys()
        top_week = await self.db.list_flag_players_top_points_weekly(guild.id, week_key, limit=1)
        top_month = await self.db.list_flag_players_top_points_monthly(guild.id, month_key, limit=1)
        weekly_leader = "Noch kein Eintrag"
        monthly_leader = "Noch kein Eintrag"
        if top_week:
            uid = int(top_week[0][0])
            points = int(top_week[0][1] or 0)
            member = guild.get_member(uid)
            weekly_leader = f"**{member.display_name if member else uid}** ({points} Punkte)"
        if top_month:
            uid = int(top_month[0][0])
            points = int(top_month[0][1] or 0)
            member = guild.get_member(uid)
            monthly_leader = f"**{member.display_name if member else uid}** ({points} Punkte)"
        players = await self.db.count_flag_players(guild.id)
        rounds = await self.db.sum_flag_rounds(guild.id)
        best_streak = await self.db.best_flag_streak(guild.id)
        return {
            "players": int(players),
            "rounds": int(rounds),
            "best_streak": int(best_streak),
            "weekly_leader": weekly_leader,
            "monthly_leader": monthly_leader,
        }

    async def sync_king_role(self, guild: discord.Guild):
        role_id = int(self.settings.get_guild_int(guild.id, "flags.king_role_id", 0) or 0)
        if not role_id:
            return
        role = guild.get_role(role_id)
        if not role:
            return

        leader_id = 0
        week_key, _ = self._period_keys()
        rows = await self.db.list_flag_players_top_points_weekly(guild.id, week_key, limit=1)
        if rows:
            leader_id = int(rows[0][0] or 0)
        if not leader_id:
            return

        leader = guild.get_member(leader_id)
        if not leader:
            try:
                leader = await guild.fetch_member(leader_id)
            except Exception:
                leader = None
        if not isinstance(leader, discord.Member):
            return

        try:
            me = guild.me or guild.get_member(getattr(self.bot.user, "id", 0))
            if me and role >= me.top_role:
                return
        except Exception:
            return

        for member in list(role.members):
            if int(member.id) == int(leader.id):
                continue
            try:
                await member.remove_roles(role, reason="Flaggenkönig aktualisiert")
            except Exception:
                pass

        if role not in leader.roles:
            try:
                await leader.add_roles(role, reason="Flaggenkönig (Platz 1)")
            except Exception:
                pass

    async def refresh_dashboard(self, guild: discord.Guild):
        state = await self._guild_state(guild.id)
        cid = int(state.get("channel_id", 0))
        if not cid:
            return
        ch = guild.get_channel(cid)
        if not ch:
            try:
                ch = await guild.fetch_channel(cid)
            except Exception:
                ch = None
        if not isinstance(ch, discord.TextChannel):
            return
        await self.ensure_dashboard(guild, ch)
        await self.sync_king_role(guild)

    async def ensure_dashboard(self, guild: discord.Guild, channel: discord.TextChannel):
        if not self._enabled(guild.id):
            return
        state = await self._guild_state(guild.id)
        stats = await self._dashboard_stats(guild)
        view = self.build_dashboard_view(guild, stats)
        mid = int(state["dashboard_message_id"])
        if mid:
            try:
                msg = await channel.fetch_message(mid)
                await msg.edit(view=view)
                return
            except Exception:
                pass
        reuse = await self._find_existing_dashboard_message(channel)
        if reuse:
            try:
                await reuse.edit(view=view)
                await self.db.set_flag_quiz_dashboard_message(guild.id, int(reuse.id))
                return
            except Exception:
                pass
        msg = await channel.send(view=view)
        await self.db.set_flag_quiz_dashboard_message(guild.id, int(msg.id))

    async def _find_existing_dashboard_message(self, channel: discord.TextChannel) -> discord.Message | None:
        me = getattr(self.bot, "user", None)
        if not me:
            return None
        try:
            async for msg in channel.history(limit=40):
                if int(msg.author.id) != int(me.id):
                    continue
                if self._is_dashboard_message(msg):
                    return msg
        except Exception:
            return None
        return None

    def _is_dashboard_message(self, msg: discord.Message) -> bool:
        try:
            for row in list(msg.components or []):
                for item in list(getattr(row, "children", []) or []):
                    cid = str(getattr(item, "custom_id", "") or "")
                    if cid.startswith("starry:flag_dash:"):
                        return True
        except Exception:
            return False
        return False

    def build_dashboard_view(self, guild: discord.Guild, stats: dict[str, Any]) -> discord.ui.LayoutView:
        from bot.modules.flags.views.flag_dashboard import FlagDashboardButton
        buttons = [
            FlagDashboardButton("normal"),
            FlagDashboardButton("easy"),
            FlagDashboardButton("daily"),
            FlagDashboardButton("bet"),
            FlagDashboardButton("leaderboard_weekly"),
            FlagDashboardButton("leaderboard_monthly"),
            FlagDashboardButton("streaks"),
        ]
        return build_dashboard_view(self.settings, guild, stats, buttons)

    async def setup_channel(self, guild: discord.Guild, channel: discord.TextChannel):
        if not self._enabled(guild.id):
            return
        await self.db.set_flag_quiz_channel(guild.id, int(channel.id))
        await self.ensure_dashboard(guild, channel)

    async def start_round(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        mode: str,
        wager_points: int = 0,
    ) -> tuple[bool, str]:
        if not self._enabled(guild.id):
            return False, "Flaggenquiz ist deaktiviert."
        await self._ensure_country_data()
        state = await self._guild_state(guild.id)
        quiz_channel_id = int(state["channel_id"])
        if quiz_channel_id and int(channel.id) != quiz_channel_id:
            return False, f"Bitte nutze den Quiz-Kanal: <#{quiz_channel_id}>"
        key = self._quiz_key(guild.id, channel.id, user.id)
        if key in self._rounds:
            return False, "Für dich läuft bereits eine Runde."
        cooldown_seconds = self._start_cooldown_seconds(guild.id)
        if cooldown_seconds > 0:
            last = self._last_round_start_at.get(key)
            if last:
                delta = (datetime.now(timezone.utc) - last).total_seconds()
                if delta < cooldown_seconds:
                    remaining = max(1, int(math.ceil(cooldown_seconds - delta)))
                    return False, f"Bitte warte noch **{remaining}s** bis zur nächsten Runde."

        mode_key = str(mode).lower()
        wager = int(wager_points or 0)
        if mode_key == "bet":
            if wager < 1:
                return False, "Der Einsatz muss mindestens 1 Punkt sein."
            max_wager = self._max_wager_points(guild.id)
            if wager > max_wager:
                return False, f"Maximaler Einsatz ist **{max_wager}** Punkte."
            ps = await self._get_player_stats(guild.id, user.id)
            self._apply_period_rollover(ps)
            if int(ps["total_points"]) < wager:
                return False, f"Du hast nicht genug Punkte. Verfügbar: {int(ps['total_points'])}."
            ps["total_points"] -= wager
            ps["weekly_points"] -= wager
            ps["monthly_points"] -= wager
            await self._save_player_stats(guild.id, user.id, ps)
        if mode_key == "daily":
            ps = await self._get_player_stats(guild.id, user.id)
            today = datetime.now(timezone.utc).date().isoformat()
            if ps.get("last_daily") == today:
                return False, "Du hast die Daily heute schon gespielt."
            code = await self._daily_code(guild.id)
        else:
            code = await self._random_code(guild.id)
        name = self._name_for(code)
        answers = self._answer_candidates_for(code, name)

        button_map: dict[str, str] = {}
        button_view_map: dict[str, tuple[str, str]] = {}
        if mode_key == "easy":
            options = {code}
            available_codes = await self._available_codes(guild.id)
            while len(options) < 4 and len(options) < len(available_codes):
                options.add(await self._random_code(guild.id))
            opts = list(options)
            random.shuffle(opts)
            for c in opts:
                cid = f"starry:flag_easy:{guild.id}:{channel.id}:{user.id}:{c}"
                button_map[cid] = c
                button_view_map[cid] = (c, self._name_for(c))

        fs = await self._get_flag_stats(guild.id, code)
        fs["asked"] += 1
        await self._save_flag_stats(guild.id, code, fs)
        flag_url = self._flag_url_for(code)
        time_limit_seconds = self.TIME_LIMIT_BET_SECONDS if mode_key == "bet" else self.TIME_LIMIT_SECONDS
        end_at = datetime.now(timezone.utc) + timedelta(seconds=time_limit_seconds)

        emb = build_round_embed(
            self.settings,
            guild,
            user.id,
            name,
            code,
            flag_url,
            mode_key,
            end_at=end_at,
            wager_points=wager,
            time_limit_seconds=time_limit_seconds,
            asked=int(fs["asked"]),
            correct=int(fs["correct"]),
            wrong=int(fs["wrong"]),
        )
        view = None
        if button_map:
            from bot.modules.flags.views.flag_dashboard import FlagEasyAnswerView
            view = FlagEasyAnswerView(button_view_map)
        msg = await channel.send(embed=emb, view=view, delete_after=30)
        self._last_round_start_at[key] = datetime.now(timezone.utc)
        self._remember_recent_code(guild.id, code)

        round_ = ActiveRound(
            guild.id,
            channel.id,
            user.id,
            mode_key,
            code,
            flag_url,
            answers,
            button_map,
            int(msg.id),
            None,
            end_at,
            wager,
        )
        self._rounds[key] = round_

        async def _timeout():
            await asyncio.sleep(time_limit_seconds)
            claimed = await self._claim_round(key, round_)
            if not claimed:
                return
            ps = await self._get_player_stats(guild.id, user.id)
            self._apply_period_rollover(ps)
            ps["wrong"] += 1
            ps["current_streak"] = 0
            await self._save_player_stats(guild.id, user.id, ps)
            fstats = await self._get_flag_stats(guild.id, code)
            fstats["wrong"] += 1
            await self._save_flag_stats(guild.id, code, fstats)
            await channel.send(
                embed=build_result_embed(
                    self.settings,
                    guild,
                    False,
                    user.id,
                    name,
                    code,
                    flag_url,
                    -wager if mode_key == "bet" else 0,
                    int(ps["total_points"]),
                    int(ps["current_streak"]),
                    asked=int(fstats["asked"]),
                    right_total=int(fstats["correct"]),
                    wrong_total=int(fstats["wrong"]),
                ),
                view=self._build_replay_view(),
                delete_after=30,
            )
            await self.refresh_dashboard(guild)

        task = asyncio.create_task(_timeout())
        round_.task = task
        if mode_key == "bet":
            return True, f"Custom-Runde gestartet mit **{wager}** Einsatz (15s)."
        return True, "Runde gestartet."

    async def start_bet_round(
        self,
        guild: discord.Guild,
        channel: discord.TextChannel,
        user: discord.Member,
        wager_points: int,
    ) -> tuple[bool, str]:
        return await self.start_round(guild, channel, user, "bet", wager_points=wager_points)

    async def handle_text_answer(self, message: discord.Message):
        if not message.guild or not isinstance(message.channel, discord.TextChannel):
            return
        if not self._enabled(message.guild.id):
            return
        if not isinstance(message.author, discord.Member) or message.author.bot:
            return
        state = await self._guild_state(message.guild.id)
        if int(state["channel_id"] or 0) and int(message.channel.id) != int(state["channel_id"]):
            return
        content = str(message.content or "").strip()
        if content.startswith("!"):
            return
        key = self._quiz_key(message.guild.id, message.channel.id, message.author.id)
        round_ = self._rounds.get(key)
        if not round_:
            return
        normalized = self._normalize(content)
        by_flag_emoji = str(self._code_from_flag_emoji(content) or "").upper() == str(round_.code).upper()
        by_exact = normalized == self._normalize(round_.code) or normalized in round_.answer_names
        by_fuzzy = any(self._is_fuzzy_match(normalized, cand) for cand in round_.answer_names)
        is_correct = bool(by_flag_emoji or by_exact or by_fuzzy)
        await self._resolve_round(message.guild, message.channel, message.author, round_, is_correct)
        try:
            await message.delete()
        except Exception:
            pass

    async def handle_easy_button(self, interaction: discord.Interaction, code: str):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel) or not interaction.user:
            return
        if not self._enabled(interaction.guild.id):
            if interaction.response.is_done():
                await interaction.followup.send("Flaggenquiz ist deaktiviert.", ephemeral=True, delete_after=30)
            else:
                await interaction.response.send_message("Flaggenquiz ist deaktiviert.", ephemeral=True, delete_after=30)
            return
        uid = int(interaction.user.id)
        key = self._quiz_key(interaction.guild.id, interaction.channel.id, uid)
        round_ = self._rounds.get(key)
        if not round_:
            if interaction.response.is_done():
                await interaction.followup.send("Keine aktive Runde für dich.", ephemeral=True, delete_after=30)
            else:
                await interaction.response.send_message("Keine aktive Runde für dich.", ephemeral=True, delete_after=30)
            return
        await self._resolve_round(interaction.guild, interaction.channel, interaction.user, round_, str(round_.code).upper() == str(code).upper())

    async def _resolve_round(self, guild: discord.Guild, channel: discord.TextChannel, user: discord.abc.User, round_: ActiveRound, correct: bool):
        key = self._quiz_key(guild.id, channel.id, int(user.id))
        claimed = await self._claim_round(key, round_)
        if not claimed:
            return
        if round_.task:
            round_.task.cancel()
        try:
            await channel.get_partial_message(int(round_.prompt_message_id)).delete()
        except Exception:
            pass
        ps = await self._get_player_stats(guild.id, int(user.id))
        self._apply_period_rollover(ps)
        name = self._name_for(round_.code)
        if correct:
            if round_.mode == "daily":
                gain = self._points_for_mode(guild.id, "daily")
            elif round_.mode == "easy":
                gain = self._points_for_mode(guild.id, "easy")
            elif round_.mode == "bet":
                gain = min(int(round_.wager_points) * 2, self._max_gain_per_round(guild.id))
            else:
                gain = self._points_for_mode(guild.id, "normal")
            if round_.mode != "bet":
                gain = min(int(gain), self._max_gain_per_round(guild.id))
            ps["total_points"] += gain
            ps["weekly_points"] += gain
            ps["monthly_points"] += gain
            ps["correct"] += 1
            ps["current_streak"] += 1
            ps["best_streak"] = max(int(ps["best_streak"]), int(ps["current_streak"]))
            if round_.mode == "daily":
                ps["last_daily"] = datetime.now(timezone.utc).date().isoformat()
            await self._save_player_stats(guild.id, int(user.id), ps)
            fstats = await self._get_flag_stats(guild.id, round_.code)
            fstats["correct"] += 1
            await self._save_flag_stats(guild.id, round_.code, fstats)
            await channel.send(
                embed=build_result_embed(
                    self.settings,
                    guild,
                    True,
                    int(user.id),
                    name,
                    round_.code,
                    round_.flag_url,
                    gain,
                    int(ps["total_points"]),
                    int(ps["current_streak"]),
                    asked=int(fstats["asked"]),
                    right_total=int(fstats["correct"]),
                    wrong_total=int(fstats["wrong"]),
                ),
                view=self._build_replay_view(),
                delete_after=10,
            )
            await self._check_streak_achievements(guild, user, int(ps["current_streak"]))
        else:
            ps["wrong"] += 1
            ps["current_streak"] = 0
            await self._save_player_stats(guild.id, int(user.id), ps)
            fstats = await self._get_flag_stats(guild.id, round_.code)
            fstats["wrong"] += 1
            await self._save_flag_stats(guild.id, round_.code, fstats)
            await channel.send(
                embed=build_result_embed(
                    self.settings,
                    guild,
                    False,
                    int(user.id),
                    name,
                    round_.code,
                    round_.flag_url,
                    -int(round_.wager_points) if round_.mode == "bet" else 0,
                    int(ps["total_points"]),
                    int(ps["current_streak"]),
                    asked=int(fstats["asked"]),
                    right_total=int(fstats["correct"]),
                    wrong_total=int(fstats["wrong"]),
                ),
                view=self._build_replay_view(),
                delete_after=10,
            )
        await self.sync_king_role(guild)
        await self.refresh_dashboard(guild)

    def _build_replay_view(self):
        from bot.modules.flags.views.flag_dashboard import FlagReplayView
        return FlagReplayView()

    async def _check_streak_achievements(self, guild: discord.Guild, user: discord.abc.User, current_streak: int):
        for threshold in self.STREAK_ACHIEVEMENTS:
            if int(current_streak) < int(threshold):
                continue
            code = f"flag_streak_{int(threshold)}"
            try:
                rows = await self.db.list_achievements(guild.id, int(user.id))
            except Exception:
                rows = []
            existing = {str(r[0]) for r in rows if r}
            if code in existing:
                continue
            try:
                await self.db.add_achievement(guild.id, int(user.id), code)
            except Exception:
                continue
            try:
                ch_id = (await self._guild_state(guild.id)).get("channel_id", 0)
                if not ch_id:
                    continue
                ch = guild.get_channel(int(ch_id))
                if isinstance(ch, discord.TextChannel):
                    await ch.send(f"🏅 <@{int(user.id)}> hat den Flaggen-Erfolg freigeschaltet: **{threshold}er Streak**!", delete_after=30)
            except Exception:
                pass

    async def leaderboard_text(self, guild: discord.Guild, period: str = "weekly", limit: int = 10) -> str:
        week_key, month_key = self._period_keys()
        if str(period).lower() == "monthly":
            rows = await self.db.list_flag_players_top_points_monthly(guild.id, month_key, limit=limit)
        else:
            rows = await self.db.list_flag_players_top_points_weekly(guild.id, week_key, limit=limit)
        if not rows:
            return "Noch keine Einträge."
        lines = []
        for i, row in enumerate(rows, 1):
            uid = int(row[0])
            points = int(row[1] or 0)
            member = guild.get_member(uid)
            name = member.display_name if member else str(uid)
            lines.append(f"#{i} {name} - {points} Punkte")
        return "\n".join(lines)

    async def _claim_round(self, key: tuple[int, int, int], expected: ActiveRound) -> bool:
        lock = self._resolve_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._resolve_locks[key] = lock
        async with lock:
            current = self._rounds.get(key)
            if current is None or current is not expected:
                return False
            self._rounds.pop(key, None)
            return True

    async def streaks_text(self, guild: discord.Guild, limit: int = 10) -> str:
        rows = await self.db.list_flag_players_top_streak(guild.id, limit=limit)
        if not rows:
            return "Noch keine Einträge."
        lines = []
        for i, row in enumerate(rows, 1):
            uid = int(row[0])
            cur = int(row[1] or 0)
            best = int(row[2] or 0)
            member = guild.get_member(uid)
            name = member.display_name if member else str(uid)
            lines.append(f"#{i} {name} - Streak {cur} (Best {best})")
        return "\n".join(lines)

    async def stats_for(self, guild_id: int, user_id: int) -> dict[str, Any]:
        return await self._get_player_stats(guild_id, user_id)

    async def flag_info(self, guild_id: int, query: str) -> tuple[str | None, str, dict[str, int]]:
        code = await self._resolve_code(query)
        if not code:
            return None, "", {"asked": 0, "correct": 0, "wrong": 0}
        name = self._name_for(code)
        fs = await self._get_flag_stats(guild_id, code)
        return code, name, fs

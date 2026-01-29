from __future__ import annotations

import re
import time
from datetime import datetime, timezone
import httpx
import discord


_MENTION_RE = re.compile(r"<@!?\d+>")
_PERSONA_RE = re.compile(r"\[([^\]]+)\]")
_MAX_REPLY_CHARS = 500
_CHEAPEST_MODEL = "deepseek-chat"
_DAILY_LIMIT = 20
_SESSION_TTL_SECONDS = 300

_PERSONAS: dict[str, str] = {
    "basic": "Du bist hilfreich, klar und freundlich. Antworte kurz, direkt und auf Deutsch.",
    "sauer": "Du bist genervt und leicht gereizt, aber bleibst verständlich. Antworte auf Deutsch.",
    "provokant": "Du bist provokant, frech und direkt, aber ohne echte Drohungen. Antworte auf Deutsch.",
    "beleidigend": "Du bist beleidigend und respektlos, ohne Gewaltaufrufe. Antworte auf Deutsch.",
    "verschwörerisch": "Du klingst verschwörerisch und mysteriös, als würdest du Insiderwissen haben. Antworte auf Deutsch.",
    "papperplatte": "Du sprichst locker, flapsig und ein bisschen albern, wie ein Streamer. Antworte auf Deutsch.",
    "papaplatte": "Du sprichst locker, flapsig und ein bisschen albern, wie ein Streamer. Antworte auf Deutsch.",
}


class DeepSeekService:
    def __init__(self, bot: discord.Client, settings, logger):
        self.bot = bot
        self.settings = settings
        self.logger = logger
        self._sessions: dict[tuple[int, int], dict] = {}
        self._daily_counts: dict[tuple[int, int], dict] = {}

    def _g(self, guild_id: int, key: str, default=None):
        return self.settings.get_guild(guild_id, key, default)

    def _api_key(self, guild_id: int) -> str:
        return str(self._g(guild_id, "ai.deepseek_api_key", "") or "").strip()

    def _system_prompt(self, guild_id: int) -> str:
        return str(self._g(guild_id, "ai.system_prompt", "") or "").strip()

    def _model(self, guild_id: int) -> str:
        return _CHEAPEST_MODEL

    def _endpoint(self, guild_id: int) -> str:
        return str(self._g(guild_id, "ai.endpoint", "https://api.deepseek.com/chat/completions") or "").strip()

    def _today_key(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _get_daily_state(self, guild_id: int, user_id: int) -> dict:
        key = (int(guild_id), int(user_id))
        state = self._daily_counts.get(key)
        today = self._today_key()
        if not state or state.get("date") != today:
            state = {"date": today, "count": 0}
            self._daily_counts[key] = state
        return state

    def can_consume(self, guild_id: int, user_id: int) -> bool:
        state = self._get_daily_state(guild_id, user_id)
        return int(state.get("count", 0)) < _DAILY_LIMIT

    def consume(self, guild_id: int, user_id: int) -> int:
        state = self._get_daily_state(guild_id, user_id)
        state["count"] = int(state.get("count", 0)) + 1
        return int(state["count"])

    def _get_session(self, guild_id: int, user_id: int) -> dict | None:
        key = (int(guild_id), int(user_id))
        session = self._sessions.get(key)
        if not session:
            return None
        last_at = float(session.get("last_at", 0))
        if time.time() - last_at > _SESSION_TTL_SECONDS:
            self._sessions.pop(key, None)
            return None
        return session

    def _set_session(self, guild_id: int, user_id: int, user_text: str, bot_text: str):
        key = (int(guild_id), int(user_id))
        self._sessions[key] = {
            "last_user": user_text,
            "last_bot": bot_text,
            "last_at": time.time(),
        }

    def build_messages(self, guild_id: int, user_id: int, prompt: str, persona: str | None = None) -> list[dict]:
        system_prompt = self._system_prompt(guild_id)
        messages: list[dict] = []
        persona_prompt = _PERSONAS.get(str(persona or "").strip().lower(), "")
        combined = "\n\n".join([p for p in [system_prompt, persona_prompt] if p])
        if combined:
            messages.append({"role": "system", "content": combined})
        elif system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        session = self._get_session(guild_id, user_id)
        if session:
            last_user = str(session.get("last_user") or "").strip()
            last_bot = str(session.get("last_bot") or "").strip()
            if last_user:
                messages.append({"role": "user", "content": last_user})
            if last_bot:
                messages.append({"role": "assistant", "content": last_bot})

        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate_reply(self, guild_id: int, messages: list[dict]) -> tuple[str | None, str | None]:
        api_key = self._api_key(guild_id)
        if not api_key:
            return None, "API-Key fehlt"

        model = self._model(guild_id)
        endpoint = self._endpoint(guild_id)

        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.8,
            "max_tokens": 220,
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code >= 400:
                    return None, f"HTTP {resp.status_code}"
                data = resp.json()
        except Exception:
            return None, "Request fehlgeschlagen"

        try:
            choices = data.get("choices") or []
            content = choices[0]["message"]["content"]
            reply = str(content).strip()
            if len(reply) > _MAX_REPLY_CHARS:
                reply = reply[: _MAX_REPLY_CHARS].rstrip()
            return reply, None
        except Exception:
            return None, "Antwort ungueltig"

    def clean_prompt(self, bot_user_id: int, text: str) -> str:
        if not text:
            return ""
        text = _MENTION_RE.sub("", text)
        return text.strip()

    def extract_persona(self, text: str) -> tuple[str | None, str]:
        if not text:
            return None, ""
        match = _PERSONA_RE.search(text)
        if not match:
            return None, text.strip()
        raw = match.group(1).strip().lower()
        persona = raw if raw in _PERSONAS else None
        cleaned = (text[: match.start()] + text[match.end():]).strip()
        return persona, cleaned

    def daily_limit(self) -> int:
        return _DAILY_LIMIT

    def reset_daily_limit(self, guild_id: int, user_id: int | None = None) -> int:
        if user_id is not None:
            self._daily_counts.pop((int(guild_id), int(user_id)), None)
            return 1
        removed = 0
        gid = int(guild_id)
        for key in list(self._daily_counts.keys()):
            if key[0] == gid:
                self._daily_counts.pop(key, None)
                removed += 1
        return removed

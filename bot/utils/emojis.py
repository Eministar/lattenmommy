from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import discord

_COLON = re.compile(r"^:([a-zA-Z0-9_]+):$")
_NAME = re.compile(r"^[a-zA-Z0-9_]{2,64}$")


@dataclass(frozen=True)
class AppEmoji:
    name: str
    id: int
    animated: bool = False

    def mention(self) -> str:
        return f"<a:{self.name}:{self.id}>" if self.animated else f"<:{self.name}:{self.id}>"

    def partial(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name=self.name, id=self.id, animated=self.animated)


APP: dict[str, AppEmoji] = {
    "red": AppEmoji("red", 1459689527823040617, animated=True),
    "orange": AppEmoji("orange", 1459689518365020250, animated=False),
    "nerd": AppEmoji("nerd", 1459689509758439729, animated=True),
    "money": AppEmoji("money", 1459689496831332497, animated=True),
    "info": AppEmoji("info", 1459689488040071188, animated=True),
    "hearts": AppEmoji("hearts", 1459689476870639779, animated=True),
    "green": AppEmoji("green", 1459689466728812776, animated=True),
    "discord_love": AppEmoji("discord_love", 1459689455257653299, animated=True),
    "cursor3": AppEmoji("cursor3", 1459689446118002852, animated=True),
    "cursor2": AppEmoji("cursor2", 1459689438589354076, animated=False),
    "cursor": AppEmoji("cursor", 1459689429529661571, animated=False),
    "cheers": AppEmoji("cheers", 1459689420570493011, animated=True),
    "book": AppEmoji("book", 1459689401763365043, animated=True),
    "chat": AppEmoji("chat", 1459921474289930503, animated=True),

}

ALIASES: dict[str, str] = {
    "book~1": "book",
    "arrow2": "cursor2",
}

UNICODE_FALLBACK: dict[str, str] = {
    "arrow2": "»",
}


def _resolve_key(k: str) -> str:
    k = k.strip()
    return ALIASES.get(k, k)


def _settings_override(settings: Any, key: str) -> Optional[Any]:
    try:
        block = settings.get("emojis", {}) if settings else {}
        if isinstance(block, dict) and key in block:
            return block.get(key)
    except Exception:
        pass
    return None


def em(settings: Any, key: str, guild: discord.Guild | None = None) -> str:
    k = (key or "").strip()
    if not k:
        return ""

    k = _resolve_key(k)

    ov = _settings_override(settings, k)
    if isinstance(ov, str) and ov.strip():
        s = ov.strip()


        if s.startswith("<") and s.endswith(">"):
            return s


        m = _COLON.match(s)
        if m:
            kk = _resolve_key(m.group(1))
            e = APP.get(kk)
            return e.mention() if e else ""


        if _NAME.match(s):
            kk = _resolve_key(s)
            e = APP.get(kk)
            return e.mention() if e else ""


        return ""

    if isinstance(ov, dict):
        try:
            name = str(ov.get("name") or k).strip() or k
            eid = int(ov.get("id"))
            animated = bool(ov.get("animated", False))
            return AppEmoji(name, eid, animated).mention()
        except Exception:
            return ""

    e = APP.get(k)
    if e:
        return e.mention()

    if guild:
        try:
            ge = discord.utils.get(guild.emojis, name=k)
            if ge:
                return str(ge)
        except Exception:
            pass

    return UNICODE_FALLBACK.get(k, "")

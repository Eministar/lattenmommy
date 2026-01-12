from __future__ import annotations

import time


class PenaltyEngine:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db

    def ladder_minutes(self) -> list[int]:
        v = self.settings.get("moderation.timeout_ladder_minutes", None)
        if isinstance(v, list) and all(isinstance(x, int) for x in v) and len(v) >= 1:
            return [int(x) for x in v]
        return [10, 60, 360, 1440, 10080]

    def window_days(self) -> int:
        try:
            return int(self.settings.get("moderation.escalation_window_days", 30))
        except Exception:
            return 30

    async def compute_timeout_minutes(self, guild_id: int, user_id: int) -> tuple[int, int]:
        since = int(time.time()) - (self.window_days() * 86400)
        strikes = await self.db.count_recent_infractions(int(guild_id), int(user_id), ["warn", "timeout"], since)
        ladder = self.ladder_minutes()
        idx = strikes if strikes < len(ladder) else len(ladder) - 1
        return int(ladder[idx]), int(strikes + 1)

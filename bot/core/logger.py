import os
import json
import discord

from bot.utils.formatting import build_log_embed

class StarryLogger:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db

    async def emit(self, bot: discord.Client, event: str, payload: dict):
        await self.db.log_event(event, payload)

        file_on = self.settings.get_bool("logging.to_file", True)
        if file_on:
            path = self.settings.get("logging.file_path", "data/logs.jsonl")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"event": event, "payload": payload}, ensure_ascii=False) + "\n")

        to_discord = self.settings.get_bool("logging.to_discord", True)
        log_channel_id = self.settings.get_int("bot.log_channel_id")
        if to_discord and log_channel_id:
            ch = bot.get_channel(log_channel_id)
            if ch and isinstance(ch, discord.abc.Messageable):
                emb = build_log_embed(self.settings, event, payload)
                try:
                    await ch.send(embed=emb)
                except Exception:
                    pass

    async def emit_system(self, event: str, payload: dict):
        await self.db.log_event(event, payload)

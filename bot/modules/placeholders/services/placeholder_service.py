import discord


class PlaceholderService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "placeholders.enabled", True))

    def _items(self, guild_id: int) -> list[dict]:
        return self.settings.get_guild(guild_id, "placeholders.items", []) or []

    def _render(self, template: str, values: dict) -> str:
        out = str(template or "")
        for key, val in values.items():
            out = out.replace("{" + key + "}", str(val))
        return out

    async def tick(self, guild: discord.Guild):
        if not guild or not self._enabled(guild.id):
            return
        items = self._items(guild.id)
        if not items:
            return

        members = [m for m in guild.members if not m.bot]
        members_total = len(members)
        online_count = len([m for m in members if m.status != discord.Status.offline])
        online_pct = int((online_count / members_total) * 100) if members_total else 0

        values = {
            "online_pct": online_pct,
            "online_count": online_count,
            "members_total": members_total,
        }

        for item in items:
            target = str(item.get("target", "") or "").strip().lower()
            template = str(item.get("template", "") or "")
            if not template or not target:
                continue
            rendered = self._render(template, values)

            if target == "channel_name":
                cid = int(item.get("channel_id", 0) or 0)
                ch = guild.get_channel(cid)
                if not isinstance(ch, discord.abc.GuildChannel):
                    continue
                if ch.name != rendered:
                    try:
                        await ch.edit(name=rendered, reason="Placeholders update")
                    except Exception:
                        pass

            elif target == "channel_topic":
                cid = int(item.get("channel_id", 0) or 0)
                ch = guild.get_channel(cid)
                if not ch or not hasattr(ch, "topic"):
                    continue
                if getattr(ch, "topic", None) != rendered:
                    try:
                        await ch.edit(topic=rendered, reason="Placeholders update")
                    except Exception:
                        pass

            elif target == "category_name":
                cid = int(item.get("category_id", 0) or 0)
                ch = guild.get_channel(cid)
                if not isinstance(ch, discord.CategoryChannel):
                    continue
                if ch.name != rendered:
                    try:
                        await ch.edit(name=rendered, reason="Placeholders update")
                    except Exception:
                        pass

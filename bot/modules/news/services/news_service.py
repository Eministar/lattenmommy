from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import discord
import httpx

from bot.modules.news.formatting.news_embeds import NewsItem, build_news_embed


class NewsService:
    def __init__(self, bot, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._last_check: dict[int, datetime] = {}

    async def tick(self):
        now = datetime.now(timezone.utc)
        due = []
        for guild in list(self.bot.guilds):
            if not self.settings.get_guild_bool(guild.id, "news.enabled", True):
                continue
            channel_id = self.settings.get_guild_int(guild.id, "news.channel_id", 0)
            if not channel_id:
                continue
            interval = self._interval_minutes(guild)
            last_check = self._last_check.get(guild.id)
            if last_check and (now - last_check).total_seconds() < interval * 60:
                continue
            due.append(guild)
        if not due:
            return

        item = await self._fetch_latest_item()
        for guild in due:
            try:
                await self._maybe_send_latest(guild, item, force=False)
            except Exception:
                pass
            self._last_check[guild.id] = now

    async def send_latest_news(self, guild: discord.Guild, force: bool = True) -> tuple[bool, str | None]:
        item = await self._fetch_latest_item()
        return await self._maybe_send_latest(guild, item, force=force)

    def _interval_minutes(self, guild: discord.Guild) -> float:
        try:
            return float(self.settings.get_guild(guild.id, "news.interval_minutes", 30) or 30)
        except Exception:
            return 30.0

    async def _maybe_send_latest(
        self,
        guild: discord.Guild,
        item: NewsItem | None,
        force: bool = False,
    ) -> tuple[bool, str | None]:
        if not item:
            return False, "Keine News gefunden."

        channel_id = self.settings.get_guild_int(guild.id, "news.channel_id", 0)
        if not channel_id:
            return False, "News-Channel ist nicht konfiguriert."

        channel = guild.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await guild.fetch_channel(int(channel_id))
            except Exception:
                channel = None
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.abc.Messageable)):
            return False, "News-Channel ungültig."

        last_id = str(self.settings.get_guild(guild.id, "news.last_posted_id", "") or "")
        if not force and last_id and last_id == item.id:
            return False, None

        content = self._build_ping_content(guild)
        embed = build_news_embed(self.settings, guild, item)
        await channel.send(content=content, embed=embed)

        try:
            await self.settings.set_guild_override(self.db, guild.id, "news.last_posted_id", item.id)
            if item.published_at:
                await self.settings.set_guild_override(
                    self.db,
                    guild.id,
                    "news.last_posted_at",
                    item.published_at.isoformat(),
                )
        except Exception:
            pass
        return True, None

    def _build_ping_content(self, guild: discord.Guild) -> str | None:
        role_id = self.settings.get_guild_int(guild.id, "news.ping_role_id", 0)
        if role_id:
            return f"<@&{int(role_id)}>"
        return None

    async def _fetch_latest_item(self) -> NewsItem | None:
        api_url = str(self.settings.get("news.api_url", "https://www.tagesschau.de/api2u/news") or "").strip()
        if not api_url:
            return None

        data = await self._fetch_json(api_url)
        if not data:
            return None

        items = data.get("news", [])
        for raw in items:
            if not isinstance(raw, dict):
                continue
            if str(raw.get("type") or "").lower() == "video":
                continue
            title = str(raw.get("title") or "").strip()
            if not title:
                continue
            url = (
                str(raw.get("shareURL") or "").strip()
                or str(raw.get("detailsweb") or "").strip()
                or str(raw.get("details") or "").strip()
            )
            if not url:
                continue
            desc = (
                str(raw.get("firstSentence") or "").strip()
                or str(raw.get("teaserText") or "").strip()
                or str(raw.get("topline") or "").strip()
                or title
            )
            image_url = self._pick_image_url(raw)
            published_at = self._parse_date(raw.get("date"))
            item_id = str(raw.get("externalId") or raw.get("sophoraId") or url or title).strip()
            return NewsItem(
                id=item_id,
                title=title,
                description=desc,
                url=url,
                image_url=image_url,
                published_at=published_at,
            )
        return None

    async def _fetch_json(self, url: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "StarryBot/1.0"})
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    def _parse_date(self, value: Any) -> datetime | None:
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value))
        except Exception:
            return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _pick_image_url(self, raw: dict) -> str | None:
        image = raw.get("teaserImage") or {}
        if not isinstance(image, dict):
            return None
        variants = image.get("imageVariants") or {}
        if isinstance(variants, dict):
            preferred = [
                "16x9-960",
                "16x9-640",
                "16x9-512",
                "16x9-384",
                "1x1-640",
                "1x1-512",
                "1x1-432",
                "1x1-256",
                "1x1-144",
            ]
            for key in preferred:
                url = variants.get(key)
                if url:
                    return str(url)
            for url in variants.values():
                if url:
                    return str(url)
        return None

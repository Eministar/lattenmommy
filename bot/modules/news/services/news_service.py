from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import re
import time
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import discord
import httpx

from bot.modules.news.formatting.news_embeds import NewsItem, build_news_view


_YT_CHANNEL_RE = re.compile(r'"channelId":"(UC[^"]+)"')
_YT_EXTERNAL_RE = re.compile(r'"externalId":"(UC[^"]+)"')
_YT_CHANNEL_URL_RE = re.compile(r"/channel/(UC[a-zA-Z0-9_-]{16,})")
_YT_USER_URL_RE = re.compile(r"/user/([^/?#]+)")
_YT_HANDLE_URL_RE = re.compile(r"/@([^/?#]+)")


class NewsService:
    def __init__(self, bot, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger
        self._last_check: dict[int, datetime] = {}
        self._yt_cache: dict[str, tuple[str, float]] = {}
        self._last_stats_check: dict[int, datetime] = {}

    def _youtube_stats_enabled(self, guild_id: int) -> bool:
        return self.settings.get_guild_bool(guild_id, "news.youtube_stats_enabled", False)

    async def tick(self):
        now = datetime.now(timezone.utc)
        due = []
        for guild in list(self.bot.guilds):
            if not self.settings.get_guild_bool(guild.id, "news.enabled", True):
                continue
            interval = self._interval_minutes(guild)
            last_check = self._last_check.get(guild.id)
            if last_check and (now - last_check).total_seconds() < interval * 60:
                continue
            due.append(guild)
        if not due:
            return

        for guild in due:
            try:
                await self._process_guild(guild)
            except Exception:
                pass
            self._last_check[guild.id] = now
            try:
                await self._maybe_update_youtube_stats(guild)
            except Exception:
                pass

    async def send_latest_news(self, guild: discord.Guild, force: bool = True) -> tuple[bool, str | None]:
        items = await self._fetch_latest_items(guild)
        if not items:
            return False, "Keine News gefunden."
        ok = False
        err = None
        for source_key, item, source in items:
            sent, err = await self._maybe_send_latest(guild, source_key, item, force=force, source=source)
            ok = ok or sent
        return ok, err

    async def send_latest_youtube(self, guild: discord.Guild, handle: str) -> tuple[bool, str | None]:
        source = self._find_youtube_source(guild, handle)
        if not source:
            source = await self._resolve_youtube_input_source(handle)
            if not source:
                return False, "YouTube-Quelle nicht gefunden."
        source_key = self._source_key(source, 0)
        item = await self._fetch_latest_source(guild, source)
        if not item:
            return False, "Kein Video gefunden."
        return await self._maybe_send_latest(guild, source_key, item, force=True, source=source)

    def _interval_minutes(self, guild: discord.Guild) -> float:
        try:
            return float(self.settings.get_guild(guild.id, "news.interval_minutes", 30) or 30)
        except Exception:
            return 30.0

    async def _process_guild(self, guild: discord.Guild):
        items = await self._fetch_latest_items(guild)
        for source_key, item, source in items:
            try:
                await self._maybe_send_latest(guild, source_key, item, force=False, source=source)
            except Exception:
                pass

    async def _maybe_send_latest(
        self,
        guild: discord.Guild,
        source_key: str,
        item: NewsItem | None,
        force: bool = False,
        source: dict | None = None,
    ) -> tuple[bool, str | None]:
        if not item:
            return False, "Keine News gefunden."

        channel = await self._resolve_target_channel(guild, source)
        if channel is None:
            return False, "News-Channel ist nicht konfiguriert."

        last_map = self.settings.get_guild(guild.id, "news.last_posted_ids", {}) or {}
        last_id = str(last_map.get(source_key, "") or "")
        if not force and last_id and last_id == item.id:
            return False, None

        ping_text = self._build_ping_content(guild, source)
        view = build_news_view(self.settings, guild, item, ping_text=ping_text)
        msg = await channel.send(view=view)

        try:
            last_map[str(source_key)] = item.id
            await self.settings.set_guild_override(self.db, guild.id, "news.last_posted_ids", last_map)
            await self.settings.set_guild_override(self.db, guild.id, "news.last_posted_id", item.id)
            if item.published_at:
                await self.settings.set_guild_override(
                    self.db,
                    guild.id,
                    "news.last_posted_at",
                    item.published_at.isoformat(),
                )
            if item.video_id:
                await self._store_youtube_alert(guild, item, channel.id, msg.id)
        except Exception:
            pass
        return True, None

    async def _resolve_target_channel(self, guild: discord.Guild, source: dict | None = None):
        src_channel_id = 0
        if isinstance(source, dict):
            try:
                src_channel_id = int(source.get("channel_id") or 0)
            except Exception:
                src_channel_id = 0
        channel_id = src_channel_id or self.settings.get_guild_int(guild.id, "news.channel_id", 0)
        if not channel_id:
            return None
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await guild.fetch_channel(int(channel_id))
            except Exception:
                channel = None
        if not isinstance(channel, (discord.TextChannel, discord.Thread, discord.abc.Messageable)):
            return None
        return channel

    def _build_ping_content(self, guild: discord.Guild, source: dict | None = None) -> str | None:
        role_id = 0
        if isinstance(source, dict):
            try:
                role_id = int(source.get("ping_role_id") or 0)
            except Exception:
                role_id = 0
        if not role_id:
            role_id = self.settings.get_guild_int(guild.id, "news.ping_role_id", 0)
        if role_id:
            return f"<@&{int(role_id)}>"
        return None

    async def _fetch_latest_items(self, guild: discord.Guild) -> list[tuple[str, NewsItem, dict | None]]:
        sources = self.settings.get_guild(guild.id, "news.sources", None)
        if not sources:
            api_url = str(self.settings.get_guild(guild.id, "news.api_url", "https://www.tagesschau.de/api2u/news") or "").strip()
            item = await self._fetch_latest_tagesschau(api_url)
            return [("tagesschau", item, None)] if item else []

        results: list[tuple[str, NewsItem, dict | None]] = []
        for idx, src in enumerate(sources):
            if not isinstance(src, dict):
                continue
            source_key = self._source_key(src, idx)
            item = await self._fetch_latest_source(guild, src)
            if item:
                results.append((source_key, item, src))
        return results

    def _source_key(self, src: dict, idx: int) -> str:
        if src.get("id"):
            return str(src.get("id"))
        t = str(src.get("type") or "rss")
        if t == "youtube":
            handle = str(src.get("handle") or "").strip()
            channel_id = str(src.get("channel_id") or "").strip()
            return f"youtube:{handle or channel_id or idx}"
        if t == "tagesschau":
            api_url = str(src.get("api_url") or "").strip()
            return f"tagesschau:{api_url or idx}"
        url = str(src.get("url") or "").strip()
        return f"{t}:{url or idx}"

    def _find_youtube_source(self, guild: discord.Guild, handle: str) -> dict | None:
        h = str(handle or "").strip().lstrip("@").lower()
        sources = self.settings.get_guild(guild.id, "news.sources", []) or []
        for src in sources:
            if not isinstance(src, dict):
                continue
            if str(src.get("type") or "").strip().lower() != "youtube":
                continue
            name = str(src.get("name") or "").strip().lower()
            handle_val = str(src.get("handle") or "").strip().lstrip("@").lower()
            channel_id = str(src.get("channel_id") or "").strip().lower()
            if h in {name, handle_val, channel_id}:
                return src
        return None

    async def _fetch_latest_source(self, guild: discord.Guild, src: dict) -> NewsItem | None:
        t = str(src.get("type") or "rss").strip().lower()
        name = str(src.get("name") or "News").strip() or "News"
        if t == "tagesschau":
            api_url = str(src.get("api_url") or "https://www.tagesschau.de/api2u/news").strip()
            item = await self._fetch_latest_tagesschau(api_url)
            if item:
                return NewsItem(
                    id=item.id,
                    title=item.title,
                    description=item.description,
                    url=item.url,
                    image_url=item.image_url,
                    published_at=item.published_at,
                    source=name,
                )
            return None

        if t == "youtube":
            item = await self._fetch_latest_youtube(guild, src)
            if not item:
                return None
            return NewsItem(
                id=item.id,
                title=item.title,
                description=item.description,
                url=item.url,
                image_url=item.image_url,
                published_at=item.published_at,
                source=name,
                video_id=item.video_id,
                stats=item.stats,
            )

        if t == "rss":
            url = str(src.get("url") or "").strip()
            if not url:
                return None
            item = await self._fetch_latest_rss(url)
            if not item:
                return None
            return NewsItem(
                id=item.id,
                title=item.title,
                description=item.description,
                url=item.url,
                image_url=item.image_url,
                published_at=item.published_at,
                source=name,
            )

        return None

    async def _fetch_latest_tagesschau(self, api_url: str) -> NewsItem | None:
        api_url = str(api_url or "").strip()
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
                source="Tagesschau",
            )
        return None

    async def _fetch_latest_rss(self, url: str) -> NewsItem | None:
        xml = await self._fetch_text(url)
        if not xml:
            return None
        try:
            root = ET.fromstring(xml)
        except Exception:
            return None

        channel = root.find("channel") if root.tag == "rss" else None
        if channel is None:
            channel = root
        items = channel.findall("item") if channel is not None else []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            guid = (item.findtext("guid") or link or title).strip()
            desc = (item.findtext("description") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            image_url = self._find_media_url(item)
            if not title or not link:
                continue
            return NewsItem(
                id=guid or link,
                title=title,
                description=self._strip_html(desc) or title,
                url=link,
                image_url=image_url,
                published_at=self._parse_rss_date(pub_date),
                source="RSS",
            )
        return None

    async def _fetch_latest_youtube(self, guild: discord.Guild, src: dict) -> NewsItem | None:
        feed_url = await self._resolve_youtube_feed_url(src)
        if not feed_url:
            return None
        xml = await self._fetch_text(feed_url)
        if not xml:
            return None
        try:
            root = ET.fromstring(xml)
        except Exception:
            return None

        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
            "media": "http://search.yahoo.com/mrss/",
        }

        for entry in root.findall("atom:entry", ns):
            title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = str(link_el.attrib.get("href") if link_el is not None else "").strip()
            video_id = (entry.findtext("yt:videoId", default="", namespaces=ns) or "").strip()
            entry_id = (entry.findtext("atom:id", default="", namespaces=ns) or "").strip()
            published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
            summary = (entry.findtext("atom:summary", default="", namespaces=ns) or "").strip()
            thumb = ""
            media_group = entry.find("media:group", ns)
            if media_group is not None:
                thumb_el = media_group.find("media:thumbnail", ns)
                if thumb_el is not None:
                    thumb = str(thumb_el.attrib.get("url") or "").strip()

            if not link and video_id:
                link = f"https://www.youtube.com/watch?v={video_id}"
            if not title or not link:
                continue
            item_id = video_id or entry_id or link
            stats = None
            channel = None
            access_key = self._socialkit_access_key(guild.id)
            base_url = self._socialkit_endpoint(guild.id)
            if self._youtube_stats_enabled(guild.id) and access_key and link:
                stats = await self._fetch_youtube_stats(link, access_key, base_url)
                channel_url = str(stats.get("channel_url") if stats else "").strip()
                channel = await self._fetch_youtube_channel_stats(channel_url, access_key, base_url) if channel_url else None
            return NewsItem(
                id=item_id,
                title=title,
                description=summary or "Neues Video veröffentlicht.",
                url=link,
                image_url=thumb or None,
                published_at=self._parse_date(published),
                source="YouTube",
                video_id=video_id or None,
                stats=stats,
                channel=channel,
            )
        return None

    async def _resolve_youtube_input_source(self, value: str) -> dict | None:
        raw = str(value or "").strip()
        if not raw:
            return None
        h = raw.strip().lstrip("@")
        if raw.startswith("UC"):
            return {"type": "youtube", "name": raw, "channel_id": raw}
        if raw.startswith("@"):
            return {"type": "youtube", "name": raw, "handle": h}
        if "youtube.com" in raw or "youtu.be" in raw:
            channel_id = self._extract_channel_id_from_url(raw)
            if channel_id:
                return {"type": "youtube", "name": raw, "channel_id": channel_id}
            handle = self._extract_handle_from_url(raw)
            if handle:
                return {"type": "youtube", "name": raw, "handle": handle}
            user = self._extract_user_from_url(raw)
            if user:
                return {"type": "youtube", "name": raw, "user": user}
            channel_id = await self._resolve_channel_id_from_page(raw)
            if channel_id:
                return {"type": "youtube", "name": raw, "channel_id": channel_id}
        return {"type": "youtube", "name": raw, "handle": h}

    def _extract_channel_id_from_url(self, url: str) -> str | None:
        m = _YT_CHANNEL_URL_RE.search(str(url))
        return m.group(1) if m else None

    def _extract_handle_from_url(self, url: str) -> str | None:
        m = _YT_HANDLE_URL_RE.search(str(url))
        return m.group(1) if m else None

    def _extract_user_from_url(self, url: str) -> str | None:
        m = _YT_USER_URL_RE.search(str(url))
        return m.group(1) if m else None

    async def _resolve_channel_id_from_page(self, url: str) -> str | None:
        target = str(url)
        if "youtube.com" in target and "ucbcb=1" not in target:
            joiner = "&" if "?" in target else "?"
            target = f"{target}{joiner}ucbcb=1"
        html = await self._fetch_text(target)
        if not html:
            return None
        m = _YT_CHANNEL_RE.search(html) or _YT_EXTERNAL_RE.search(html)
        if not m:
            return None
        return m.group(1)

    async def _resolve_youtube_feed_url(self, src: dict) -> str | None:
        channel_id = str(src.get("channel_id") or "").strip()
        handle = str(src.get("handle") or "").strip().lstrip("@")
        user = str(src.get("user") or "").strip()
        url = str(src.get("url") or src.get("channel_url") or "").strip()

        if channel_id:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        if user:
            return f"https://www.youtube.com/feeds/videos.xml?user={user}"
        if url:
            channel_id = self._extract_channel_id_from_url(url)
            if channel_id:
                return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            handle = self._extract_handle_from_url(url) or handle
            user = self._extract_user_from_url(url) or user
            if user:
                return f"https://www.youtube.com/feeds/videos.xml?user={user}"
        if not handle:
            return None

        cached = self._yt_cache.get(handle)
        if cached and (time.time() - cached[1]) < 21600:
            return f"https://www.youtube.com/feeds/videos.xml?channel_id={cached[0]}"

        url = f"https://www.youtube.com/@{handle}?ucbcb=1"
        html = await self._fetch_text(url)
        if not html:
            return None
        m = _YT_CHANNEL_RE.search(html) or _YT_EXTERNAL_RE.search(html)
        if not m:
            return None
        channel_id = m.group(1)
        self._yt_cache[handle] = (channel_id, time.time())
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    def _socialkit_access_key(self, guild_id: int) -> str:
        return str(self.settings.get_guild(guild_id, "news.socialkit_access_key", "") or "").strip()

    def _socialkit_endpoint(self, guild_id: int) -> str:
        return str(self.settings.get_guild(guild_id, "news.socialkit_endpoint", "https://api.socialkit.dev") or "").strip()

    async def _fetch_youtube_stats(self, video_url: str, access_key: str, base_url: str) -> dict | None:
        if not video_url or not access_key or not base_url:
            return None
        url = f"{base_url.rstrip('/')}/youtube/stats"
        params = {"access_key": access_key, "url": video_url}
        data = await self._fetch_json(url, params=params)
        if not data:
            return None
        try:
            views = int(data.get("viewCount") or data.get("views") or 0)
        except Exception:
            views = 0
        try:
            likes = int(data.get("likeCount") or data.get("likes") or 0)
        except Exception:
            likes = 0
        return {
            "views": views,
            "likes": likes,
            "channel_name": str(data.get("channelName") or data.get("channel") or ""),
            "channel_url": str(data.get("channelLink") or data.get("channelUrl") or ""),
            "thumbnail_url": str(data.get("thumbnailUrl") or data.get("thumbnail") or ""),
        }

    async def _fetch_youtube_channel_stats(self, channel_url: str, access_key: str, base_url: str) -> dict | None:
        if not channel_url or not access_key or not base_url:
            return None
        url = f"{base_url.rstrip('/')}/youtube/channel-stats"
        params = {"access_key": access_key, "url": channel_url}
        data = await self._fetch_json(url, params=params)
        if not data:
            return None
        try:
            subs = int(data.get("subscriberCount") or data.get("subscribers") or 0)
        except Exception:
            subs = 0
        return {
            "name": str(data.get("channelName") or data.get("name") or ""),
            "url": str(data.get("channelLink") or data.get("profileUrl") or channel_url),
            "avatar_url": str(data.get("avatar") or data.get("avatarUrl") or ""),
            "subscribers": subs,
        }

    async def _store_youtube_alert(self, guild: discord.Guild, item: NewsItem, channel_id: int, message_id: int):
        alerts = self.settings.get_guild(guild.id, "news.youtube_alerts", {}) or {}
        if not item.video_id:
            return
        stats = item.stats or {}
        channel = item.channel or {}
        alerts[str(item.video_id)] = {
            "video_id": str(item.video_id),
            "message_id": int(message_id),
            "channel_id": int(channel_id),
            "title": item.title,
            "description": item.description,
            "url": item.url,
            "image_url": item.image_url,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "source": item.source,
            "stats": stats,
            "channel_name": channel.get("name"),
            "channel_url": channel.get("url"),
            "channel_avatar": channel.get("avatar_url"),
            "channel_subscribers": channel.get("subscribers"),
            "last_stats_at": None,
        }
        await self.settings.set_guild_override(self.db, guild.id, "news.youtube_alerts", alerts)

    async def _maybe_update_youtube_stats(self, guild: discord.Guild):
        if not self._youtube_stats_enabled(guild.id):
            return
        access_key = self._socialkit_access_key(guild.id)
        base_url = self._socialkit_endpoint(guild.id)
        if not access_key or not base_url:
            return
        now = datetime.now(timezone.utc)
        last = self._last_stats_check.get(guild.id)
        if last and (now - last).total_seconds() < 3600:
            return
        self._last_stats_check[guild.id] = now

        alerts = self.settings.get_guild(guild.id, "news.youtube_alerts", {}) or {}
        if not isinstance(alerts, dict) or not alerts:
            return
        updated = False
        for video_id, payload in list(alerts.items()):
            if not isinstance(payload, dict):
                continue
            msg_id = int(payload.get("message_id") or 0)
            chan_id = int(payload.get("channel_id") or 0)
            if not msg_id or not chan_id:
                continue
            video_url = str(payload.get("url") or "").strip()
            if not video_url:
                continue
            stats = await self._fetch_youtube_stats(video_url, access_key, base_url)
            if not stats:
                continue
            payload["stats"] = stats
            channel_url = str(payload.get("channel_url") or stats.get("channel_url") or "").strip()
            if channel_url:
                channel = await self._fetch_youtube_channel_stats(channel_url, access_key, base_url)
                if channel:
                    payload["channel_name"] = channel.get("name")
                    payload["channel_url"] = channel.get("url")
                    payload["channel_avatar"] = channel.get("avatar_url")
                    payload["channel_subscribers"] = channel.get("subscribers")
            payload["last_stats_at"] = now.isoformat()
            alerts[str(video_id)] = payload

            channel = guild.get_channel(chan_id)
            if channel is None:
                try:
                    channel = await guild.fetch_channel(chan_id)
                except Exception:
                    channel = None
            if not channel or not isinstance(channel, discord.abc.Messageable):
                continue
            if not hasattr(channel, "fetch_message"):
                continue
            try:
                msg = await channel.fetch_message(msg_id)
            except Exception:
                continue

            published_at = self._parse_date(payload.get("published_at"))
            item = NewsItem(
                id=str(video_id),
                title=str(payload.get("title") or "YouTube"),
                description=str(payload.get("description") or ""),
                url=str(payload.get("url") or ""),
                image_url=str(payload.get("image_url") or "") or None,
                published_at=published_at,
                source=str(payload.get("source") or "YouTube"),
                video_id=str(video_id),
                stats=stats,
                channel={
                    "name": payload.get("channel_name"),
                    "url": payload.get("channel_url"),
                    "avatar_url": payload.get("channel_avatar"),
                    "subscribers": payload.get("channel_subscribers"),
                },
            )
            ping_text = self._build_ping_content(guild)
            view = build_news_view(self.settings, guild, item, ping_text=ping_text)
            try:
                await msg.edit(view=view)
                updated = True
            except Exception:
                pass
        if updated:
            try:
                await self.settings.set_guild_override(self.db, guild.id, "news.youtube_alerts", alerts)
            except Exception:
                pass

    async def _fetch_json(self, url: str, params: dict | None = None) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers={"User-Agent": "StarryBot/1.0"})
                resp.raise_for_status()
                return resp.json()
        except Exception:
            return None

    async def _fetch_text(self, url: str) -> str | None:
        try:
            headers = {"User-Agent": "StarryBot/1.0"}
            if "youtube.com" in url or "youtu.be" in url:
                headers = {"User-Agent": "Mozilla/5.0"}
            async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                return resp.text
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

    def _parse_rss_date(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            dt = parsedate_to_datetime(str(value))
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

    def _strip_html(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _find_media_url(self, node: ET.Element) -> str | None:
        for child in node:
            tag = child.tag.lower()
            if tag.endswith("thumbnail") or tag.endswith("content"):
                url = child.attrib.get("url")
                if url:
                    return str(url)
            if tag.endswith("enclosure"):
                url = child.attrib.get("url")
                if url:
                    return str(url)
        return None

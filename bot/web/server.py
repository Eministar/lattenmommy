import os
import json
import asyncio
import time
import secrets
import discord
import httpx
from datetime import timedelta
from urllib.parse import urlencode
from fastapi import FastAPI, Request, HTTPException, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from bot.modules.tickets.services.ticket_service import TicketService
from bot.modules.moderation.services.mod_service import ModerationService
from bot.modules.birthdays.services.birthday_service import BirthdayService


class WebServer:
    def __init__(self, settings, db, bot):
        self.settings = settings
        self.db = db
        self.bot = bot
        self.ticket_service = TicketService(bot, settings, db, getattr(bot, "logger", None))
        self.moderation_service = ModerationService(bot, settings, db, getattr(bot, "forum_logs", None))
        self.birthday_service = getattr(bot, "birthday_service", None) or BirthdayService(bot, settings, db, getattr(bot, "logger", None))
        self.app = FastAPI()
        self._server = None
        self._task = None

        base = os.path.dirname(__file__)
        static_dir = os.path.join(base, "static")

        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @self.app.get("/")
        async def index():
            return FileResponse(os.path.join(static_dir, "index.html"))

        @self.app.get("/login")
        async def login():
            auth_url = self._discord_oauth_url()
            return RedirectResponse(auth_url)

        @self.app.get("/logout")
        async def logout(request: Request):
            session_id = request.cookies.get(self._session_cookie_name())
            if session_id:
                await self.db.delete_dashboard_session(session_id)
            resp = RedirectResponse("/")
            resp.delete_cookie(self._session_cookie_name())
            return resp

        @self.app.get("/oauth/callback")
        async def oauth_callback(request: Request, code: str | None = None):
            if not code:
                raise HTTPException(status_code=400, detail="Missing code")
            token_data = await self._exchange_code(code)
            access_token = token_data.get("access_token")
            refresh_token = token_data.get("refresh_token")
            expires_in = int(token_data.get("expires_in") or 0)
            if not access_token or not expires_in:
                raise HTTPException(status_code=400, detail="OAuth failed")

            user = await self._fetch_user(access_token)
            guilds = await self._fetch_guilds(access_token)

            session_id = secrets.token_urlsafe(32)
            expires_at = int(time.time()) + int(expires_in)
            await self.db.upsert_dashboard_session(
                session_id=session_id,
                user_id=int(user.get("id")),
                username=str(user.get("username")),
                avatar=str(user.get("avatar") or ""),
                access_token=str(access_token),
                refresh_token=str(refresh_token) if refresh_token else None,
                expires_at=expires_at,
                guilds_json=json.dumps(guilds, ensure_ascii=False),
            )

            resp = RedirectResponse("/")
            resp.set_cookie(
                self._session_cookie_name(),
                session_id,
                httponly=True,
                samesite="lax",
                max_age=int(expires_in),
            )
            return resp

        @self.app.get("/api/me")
        async def me(request: Request):
            session = await self._require_session(request)
            return JSONResponse(self._session_payload(session))

        @self.app.get("/api/guilds")
        async def list_guilds(request: Request):
            session = await self._require_session(request)
            return JSONResponse(self._accessible_guilds(session))

        @self.app.get("/api/global/summary")
        async def global_summary(request: Request):
            await self._require_session(request)
            tickets = await self.db.count_tickets_by_status()
            giveaways = await self.db.count_giveaways()
            polls = await self.db.count_polls()
            applications = await self.db.count_applications()
            birthdays = await self.db.count_birthdays_global()
            return JSONResponse({
                "tickets": tickets,
                "giveaways": giveaways,
                "polls": polls,
                "applications": applications,
                "birthdays": birthdays,
            })

        @self.app.get("/api/guilds/{guild_id}/summary")
        async def guild_summary(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            tickets = await self.db.count_tickets_by_status_for_guild(int(guild_id))
            giveaways = await self.db.count_giveaways(int(guild_id))
            polls = await self.db.count_polls(int(guild_id))
            applications = await self.db.count_applications(int(guild_id))
            return JSONResponse({
                "tickets": tickets,
                "giveaways": giveaways,
                "polls": polls,
                "applications": applications,
            })

        @self.app.get("/api/guilds/{guild_id}/settings")
        async def get_guild_settings(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            return JSONResponse(self.settings.dump_guild(int(guild_id)))

        @self.app.get("/api/guilds/{guild_id}/overrides")
        async def get_guild_overrides(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            return JSONResponse(self.settings.dump_guild_overrides(int(guild_id)))

        @self.app.put("/api/guilds/{guild_id}/overrides")
        async def put_guild_overrides(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            data = await request.json()
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="Invalid settings payload")
            await self.settings.replace_guild_overrides(self.db, int(guild_id), data)
            return JSONResponse({"ok": True})

        @self.app.get("/api/guilds/{guild_id}/tickets")
        async def list_tickets(request: Request, guild_id: int, limit: int = 200):
            await self._require_guild_access(request, guild_id)
            rows = await self.db.list_tickets_for_guild(int(guild_id), limit=limit)
            out = []
            for r in rows:
                out.append({
                    "id": r[0],
                    "user_id": r[1],
                    "thread_id": r[2],
                    "status": r[3],
                    "claimed_by": r[4],
                    "created_at": r[5],
                    "closed_at": r[6],
                    "rating": r[7]
                })
            return JSONResponse(out)

        @self.app.get("/api/logs")
        async def list_logs(request: Request, limit: int = 200):
            await self._require_session(request)
            rows = await self.db.list_logs(limit=limit)
            out = []
            for r in rows:
                out.append({
                    "id": r[0],
                    "event": r[1],
                    "payload": r[2],
                    "created_at": r[3],
                })
            return JSONResponse(out)

        @self.app.get("/api/guilds/{guild_id}/snippets")
        async def get_snippets(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            data = self.settings.get_guild(int(guild_id), "ticket.snippets", {}) or {}
            return JSONResponse(data)

        @self.app.put("/api/guilds/{guild_id}/snippets")
        async def put_snippets(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            data = await request.json()
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="Invalid snippets payload")
            await self.settings.set_guild_override(self.db, int(guild_id), "ticket.snippets", data)
            return JSONResponse({"ok": True})

        @self.app.get("/api/guilds/{guild_id}/applications")
        async def get_applications(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            data = self.settings.get_guild(int(guild_id), "applications", {}) or {}
            return JSONResponse(data)

        @self.app.put("/api/guilds/{guild_id}/applications")
        async def put_applications(request: Request, guild_id: int):
            await self._require_guild_access(request, guild_id)
            data = await request.json()
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="Invalid applications payload")
            await self.settings.set_guild_override(self.db, int(guild_id), "applications", data)
            return JSONResponse({"ok": True})

        @self.app.get("/api/guilds/{guild_id}/applications/list")
        async def list_applications(request: Request, guild_id: int, limit: int = 200):
            await self._require_guild_access(request, guild_id)
            rows = await self.db.list_applications_for_guild(int(guild_id), limit=limit)
            out = []
            for r in rows:
                out.append({
                    "id": r[0],
                    "user_id": r[1],
                    "thread_id": r[2],
                    "status": r[3],
                    "created_at": r[4],
                    "closed_at": r[5],
                })
            return JSONResponse(out)

        @self.app.get("/api/global/birthdays")
        async def list_global_birthdays(request: Request, limit: int = 25, offset: int = 0):
            await self._require_session(request)
            rows = await self.db.list_birthdays_global(limit=limit, offset=offset)
            total = await self.db.count_birthdays_global()
            out = [{"user_id": r[0], "day": r[1], "month": r[2], "year": r[3]} for r in rows]
            return JSONResponse({"total": total, "items": out})

        @self.app.get("/api/guilds/{guild_id}/birthdays/live")
        async def live_birthdays(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            payload = await self.birthday_service.build_dashboard_payload(guild)
            return JSONResponse(payload)

        @self.app.get("/api/guilds/{guild_id}/birthdays/summary")
        async def guild_birthdays_summary(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            payload = await self.birthday_service.build_dashboard_payload(guild)
            return JSONResponse(payload)

        @self.app.websocket("/ws/logs")
        async def ws_logs(websocket: WebSocket):
            session = await self._require_socket_session(websocket)
            await websocket.accept()
            last_id = 0
            try:
                while True:
                    rows = await self.db.list_logs(limit=50)
                    rows = list(reversed(rows))
                    for r in rows:
                        if int(r[0]) <= last_id:
                            continue
                        payload = {"id": r[0], "event": r[1], "payload": r[2], "created_at": r[3]}
                        await websocket.send_json(payload)
                        last_id = int(r[0])
                    await asyncio.sleep(2.0)
            except Exception:
                try:
                    await websocket.close()
                except Exception:
                    pass

        @self.app.get("/api/guilds/{guild_id}/users/search")
        async def search_users(request: Request, guild_id: int, query: str):
            guild = await self._require_guild_access(request, guild_id)
            q = (query or "").lower()
            out = []
            for m in guild.members:
                if q in str(m.id) or q in m.name.lower() or q in m.display_name.lower():
                    out.append({"id": m.id, "name": m.name, "display_name": m.display_name})
                    if len(out) >= 25:
                        break
            return JSONResponse(out)

        @self.app.get("/api/guilds/{guild_id}/users/live")
        async def live_users(request: Request, guild_id: int, limit: int = 50):
            guild = await self._require_guild_access(request, guild_id)
            out = []
            for m in guild.members:
                if m.status in (discord.Status.online, discord.Status.idle, discord.Status.dnd):
                    out.append({
                        "id": m.id,
                        "name": m.name,
                        "display_name": m.display_name,
                        "status": str(m.status)
                    })
                if len(out) >= limit:
                    break
            return JSONResponse(out)

        @self.app.post("/api/guilds/{guild_id}/discord/message")
        async def send_message(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            channel_id = self._int(data.get("channel_id", 0))
            content = str(data.get("content", "")).strip()
            if not channel_id or not content:
                raise HTTPException(status_code=400, detail="Missing channel_id/content")
            ch = await self._channel(channel_id)
            if not ch or getattr(ch, "guild", None) != guild:
                raise HTTPException(status_code=404, detail="Channel not found")
            await ch.send(content=content)
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/discord/embed")
        async def send_embed(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            channel_id = self._int(data.get("channel_id", 0))
            title = str(data.get("title", "")).strip()
            description = str(data.get("description", "")).strip()
            color = data.get("color", None)
            footer = str(data.get("footer", "")).strip()
            thumbnail = str(data.get("thumbnail", "")).strip()
            image = str(data.get("image", "")).strip()
            fields = data.get("fields", [])
            if not channel_id or not title:
                raise HTTPException(status_code=400, detail="Missing channel_id/title")
            ch = await self._channel(channel_id)
            if not ch or getattr(ch, "guild", None) != guild:
                raise HTTPException(status_code=404, detail="Channel not found")
            c = None
            try:
                if color:
                    c = int(str(color).replace("#", ""), 16)
            except Exception:
                c = None
            emb = discord.Embed(title=title, description=description or None, color=c)
            if isinstance(fields, list):
                for f in fields[:25]:
                    try:
                        name = str(f.get("name", "")).strip()
                        value = str(f.get("value", "")).strip()
                        inline = bool(f.get("inline", False))
                        if name and value:
                            emb.add_field(name=name, value=value, inline=inline)
                    except Exception:
                        pass
            if footer:
                emb.set_footer(text=footer)
            if thumbnail:
                emb.set_thumbnail(url=thumbnail)
            if image:
                emb.set_image(url=image)
            await ch.send(embed=emb)
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/moderation/timeout")
        async def mod_timeout(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            user_id = self._int(data.get("user_id", 0))
            minutes = self._int(data.get("minutes", 0))
            moderator_id = self._int(data.get("moderator_id", 0))
            reason = str(data.get("reason", "")).strip() or None
            if not user_id:
                raise HTTPException(status_code=404, detail="User not found")
            member = guild.get_member(user_id)
            if not member:
                raise HTTPException(status_code=404, detail="Member not found")
            moderator = guild.get_member(moderator_id) if moderator_id else None
            if moderator:
                await self.moderation_service.timeout(guild, moderator, member, minutes, reason)
            else:
                until = discord.utils.utcnow() + timedelta(minutes=minutes)
                if hasattr(member, "timeout"):
                    await member.timeout(until, reason=reason)
                else:
                    await member.edit(timed_out_until=until, reason=reason)
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/moderation/kick")
        async def mod_kick(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            user_id = self._int(data.get("user_id", 0))
            moderator_id = self._int(data.get("moderator_id", 0))
            reason = str(data.get("reason", "")).strip() or None
            member = guild.get_member(user_id) if user_id else None
            if not member:
                raise HTTPException(status_code=404, detail="Member not found")
            moderator = guild.get_member(moderator_id) if moderator_id else None
            if moderator:
                await self.moderation_service.kick(guild, moderator, member, reason)
            else:
                await member.kick(reason=reason)
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/moderation/ban")
        async def mod_ban(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            user_id = self._int(data.get("user_id", 0))
            delete_days = self._int(data.get("delete_days", 0))
            moderator_id = self._int(data.get("moderator_id", 0))
            reason = str(data.get("reason", "")).strip() or None
            if not user_id:
                raise HTTPException(status_code=404, detail="User not found")
            user = await self.bot.fetch_user(user_id)
            moderator = guild.get_member(moderator_id) if moderator_id else None
            if moderator:
                await self.moderation_service.ban(guild, moderator, user, delete_days, reason)
            else:
                await guild.ban(user, reason=reason, delete_message_days=max(0, min(7, delete_days)))
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/moderation/purge")
        async def mod_purge(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            channel_id = self._int(data.get("channel_id", 0))
            amount = self._int(data.get("amount", 0))
            user_id = self._int(data.get("user_id", 0) or 0)
            moderator_id = self._int(data.get("moderator_id", 0))
            ch = await self._channel(channel_id)
            if not isinstance(ch, discord.TextChannel) or ch.guild.id != guild.id:
                raise HTTPException(status_code=404, detail="Channel not found")
            moderator = guild.get_member(moderator_id) if moderator_id else None
            if moderator:
                deleted, _err = await self.moderation_service.purge(guild, moderator, ch, amount, guild.get_member(user_id) if user_id else None)
                return JSONResponse({"ok": True, "deleted": int(deleted)})
            else:
                def check(m: discord.Message):
                    return m.author.id == user_id if user_id else True
                deleted = await ch.purge(limit=max(1, min(100, amount)), check=check, bulk=True)
                return JSONResponse({"ok": True, "deleted": len(deleted)})

        @self.app.post("/api/guilds/{guild_id}/roles/add")
        async def roles_add(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            user_id = self._int(data.get("user_id", 0))
            role_id = self._int(data.get("role_id", 0))
            member = guild.get_member(user_id)
            role = guild.get_role(role_id)
            if not member or not role:
                raise HTTPException(status_code=404, detail="Member/Role not found")
            await member.add_roles(role, reason="Dashboard")
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/roles/remove")
        async def roles_remove(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            user_id = self._int(data.get("user_id", 0))
            role_id = self._int(data.get("role_id", 0))
            member = guild.get_member(user_id)
            role = guild.get_role(role_id)
            if not member or not role:
                raise HTTPException(status_code=404, detail="Member/Role not found")
            await member.remove_roles(role, reason="Dashboard")
            return JSONResponse({"ok": True})

        @self.app.post("/api/guilds/{guild_id}/tickets/action")
        async def ticket_action(request: Request, guild_id: int):
            guild = await self._require_guild_access(request, guild_id)
            data = await request.json()
            thread_id = self._int(data.get("thread_id", 0))
            action = str(data.get("action", "")).strip()
            user_id = self._int(data.get("user_id", 0) or 0)
            actor_id = self._int(data.get("actor_id", 0) or 0)
            thread = guild.get_thread(thread_id)
            if not thread:
                fetched = await self.bot.fetch_channel(thread_id)
                thread = fetched if isinstance(fetched, discord.Thread) else None
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            actor = guild.get_member(actor_id) if actor_id else None
            if not actor:
                raise HTTPException(status_code=404, detail="Actor not found")

            if action == "close":
                ok, err = await self.ticket_service.dashboard_close_ticket(guild, thread, actor, reason=data.get("reason"))
            elif action == "claim":
                ok, err = await self.ticket_service.dashboard_set_claim(guild, thread, actor, claimed=True)
            elif action == "release":
                ok, err = await self.ticket_service.dashboard_set_claim(guild, thread, actor, claimed=False)
            elif action == "add_user":
                if not user_id:
                    raise HTTPException(status_code=400, detail="Missing user_id")
                user = await self.bot.fetch_user(user_id)
                ok, err = await self.ticket_service.dashboard_add_participant(guild, thread, actor, user)
            else:
                raise HTTPException(status_code=400, detail="Invalid action")

            if not ok:
                raise HTTPException(status_code=400, detail=err or "Ticket action failed")
            return JSONResponse({"ok": True})

    def _session_cookie_name(self) -> str:
        return "starry_session"

    def _int(self, value) -> int:
        try:
            return int(value)
        except Exception:
            return 0

    def _discord_oauth_url(self) -> str:
        client_id = str(self.settings.get("bot.dashboard.client_id", "") or "").strip()
        redirect = str(self.settings.get("bot.dashboard.redirect_uri", "") or "").strip()
        if not client_id or not redirect:
            raise HTTPException(status_code=500, detail="OAuth not configured")
        params = {
            "client_id": client_id,
            "redirect_uri": redirect,
            "response_type": "code",
            "scope": "identify guilds",
        }
        return "https://discord.com/api/oauth2/authorize?" + urlencode(params)

    async def _exchange_code(self, code: str) -> dict:
        client_id = str(self.settings.get("bot.dashboard.client_id", "") or "").strip()
        client_secret = str(self.settings.get("bot.dashboard.client_secret", "") or "").strip()
        redirect = str(self.settings.get("bot.dashboard.redirect_uri", "") or "").strip()
        if not client_id or not client_secret or not redirect:
            raise HTTPException(status_code=500, detail="OAuth not configured")
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect,
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post("https://discord.com/api/oauth2/token", data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"OAuth token failed: {resp.text}")
        return resp.json()

    async def _fetch_user(self, access_token: str) -> dict:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://discord.com/api/users/@me", headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail="Failed to fetch user")
        return resp.json()

    async def _fetch_guilds(self, access_token: str) -> list:
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get("https://discord.com/api/users/@me/guilds", headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail="Failed to fetch guilds")
        data = resp.json()
        return data if isinstance(data, list) else []

    async def _require_session(self, request: Request) -> dict:
        session_id = request.cookies.get(self._session_cookie_name())
        if not session_id:
            raise HTTPException(status_code=401, detail="Missing session")
        row = await self.db.get_dashboard_session(session_id)
        if not row:
            raise HTTPException(status_code=401, detail="Invalid session")
        expires_at = int(row[6])
        if expires_at <= int(time.time()):
            await self.db.delete_dashboard_session(session_id)
            raise HTTPException(status_code=401, detail="Session expired")
        return {
            "session_id": row[0],
            "user_id": int(row[1]),
            "username": row[2],
            "avatar": row[3],
            "access_token": row[4],
            "refresh_token": row[5],
            "expires_at": int(row[6]),
            "guilds": json.loads(row[7] or "[]"),
        }

    async def _require_socket_session(self, websocket: WebSocket) -> dict:
        session_id = websocket.cookies.get(self._session_cookie_name())
        if not session_id:
            await websocket.close(code=4401)
            raise HTTPException(status_code=401, detail="Missing session")
        row = await self.db.get_dashboard_session(session_id)
        if not row:
            await websocket.close(code=4401)
            raise HTTPException(status_code=401, detail="Invalid session")
        expires_at = int(row[6])
        if expires_at <= int(time.time()):
            await self.db.delete_dashboard_session(session_id)
            await websocket.close(code=4401)
            raise HTTPException(status_code=401, detail="Session expired")
        return {
            "session_id": row[0],
            "user_id": int(row[1]),
            "username": row[2],
            "avatar": row[3],
            "access_token": row[4],
            "refresh_token": row[5],
            "expires_at": int(row[6]),
            "guilds": json.loads(row[7] or "[]"),
        }

    def _session_payload(self, session: dict) -> dict:
        return {
            "user": {
                "id": session["user_id"],
                "username": session["username"],
                "avatar": session.get("avatar") or None,
            },
            "guilds": self._accessible_guilds(session),
        }

    def _accessible_guilds(self, session: dict) -> list[dict]:
        out = []
        for g in session.get("guilds", []):
            try:
                gid = int(g.get("id"))
            except Exception:
                continue
            perms = int(g.get("permissions") or 0)
            is_owner = bool(g.get("owner"))
            is_admin = (perms & 0x8) == 0x8
            if not (is_owner or is_admin):
                continue
            bot_guild = self.bot.get_guild(gid)
            if not bot_guild:
                continue
            out.append({
                "id": gid,
                "name": g.get("name") or bot_guild.name,
                "icon": g.get("icon"),
                "owner": is_owner,
                "permissions": perms,
                "bot_in_guild": True,
            })
        return out

    async def _require_guild_access(self, request: Request, guild_id: int) -> discord.Guild:
        session = await self._require_session(request)
        allowed = {int(g["id"]) for g in self._accessible_guilds(session)}
        gid = int(guild_id)
        if gid not in allowed:
            raise HTTPException(status_code=403, detail="Missing permissions")
        guild = self.bot.get_guild(gid)
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found")
        return guild

    async def _channel(self, channel_id: int):
        ch = self.bot.get_channel(int(channel_id))
        if ch:
            return ch
        try:
            return await self.bot.fetch_channel(int(channel_id))
        except Exception:
            return None

    async def start(self):
        host = self.settings.get("bot.dashboard.host", "0.0.0.0")
        port = int(self.settings.get("bot.dashboard.port", 8787))
        config = uvicorn.Config(self.app, host=host, port=port, log_level="warning")
        self._server = uvicorn.Server(config)
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._server.serve())

    async def stop(self):
        if self._server:
            self._server.should_exit = True
        if self._task:
            await self._task

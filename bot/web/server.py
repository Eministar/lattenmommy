import os
import json
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

class WebServer:
    def __init__(self, settings, db):
        self.settings = settings
        self.db = db
        self.app = FastAPI()
        self._server = None
        self._task = None

        base = os.path.dirname(__file__)
        static_dir = os.path.join(base, "static")

        self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @self.app.get("/")
        async def index():
            return FileResponse(os.path.join(static_dir, "index.html"))

        @self.app.get("/api/settings")
        async def get_settings(request: Request):
            self._auth(request)
            return JSONResponse(self.settings.dump())

        @self.app.put("/api/settings")
        async def put_settings(request: Request):
            self._auth(request)
            data = await request.json()
            if not isinstance(data, dict):
                raise HTTPException(status_code=400, detail="Invalid settings payload")
            await self.settings.replace_overrides(data)
            return JSONResponse({"ok": True})

        @self.app.get("/api/tickets")
        async def list_tickets(request: Request, limit: int = 200):
            self._auth(request)
            rows = await self.db.list_tickets(limit=limit)
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

    def _auth(self, request: Request):
        token = self.settings.get("bot.dashboard.token", "change-me-now")
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing token")
        if header.split("Bearer ", 1)[1].strip() != token:
            raise HTTPException(status_code=403, detail="Invalid token")

    async def start(self):
        host = self.settings.get("bot.dashboard.host", "0.0.0.0")
        port = int(self.settings.get("bot.dashboard.port", 8787))
        config = uvicorn.Config(self.app, host=host, port=port, log_level="warning")
        self._server = uvicorn.Server(config)
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._server.serve())

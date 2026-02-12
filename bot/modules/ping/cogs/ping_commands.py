from __future__ import annotations

from time import perf_counter
import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.ping.formatting.ping_embeds import build_ping_view


class PingCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _measure_db_ms(self) -> int | None:
        db = getattr(self.bot, "db", None)
        if not db:
            return None
        start = perf_counter()
        try:
            conn = (
                getattr(db, "_conn", None)
                or getattr(db, "conn", None)
                or getattr(db, "connection", None)
            )
            if conn is not None and hasattr(conn, "execute"):
                cur = await conn.execute("SELECT 1;")
            elif hasattr(db, "execute"):
                cur = await db.execute("SELECT 1;")
            else:
                return None
            try:
                await cur.fetchone()
            except Exception:
                pass
            try:
                await cur.close()
            except Exception:
                pass
            return int((perf_counter() - start) * 1000)
        except Exception:
            return None

    @app_commands.command(name="ping", description="🏓 𑁉 Bot-Latenz prüfen")
    async def ping(self, interaction: discord.Interaction):
        start = perf_counter()
        await interaction.response.defer(thinking=True)
        api_ms = int((perf_counter() - start) * 1000)
        ws_ms = int(round(float(getattr(self.bot, "latency", 0.0)) * 1000))
        db_ms = await self._measure_db_ms()
        view = build_ping_view(
            self.bot.settings,
            interaction.guild,
            ws_ms=ws_ms,
            api_ms=api_ms,
            db_ms=db_ms,
        )
        await interaction.followup.send(view=view)


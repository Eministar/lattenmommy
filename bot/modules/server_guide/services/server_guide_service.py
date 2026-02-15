from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from bot.modules.server_guide.formatting.server_guide_embeds import build_hub_embed, build_module_embed


@dataclass
class ModuleGuide:
    key: str
    title: str
    commands: list[str]


class ServerGuideService:
    def __init__(self, bot, settings, logger):
        self.bot = bot
        self.settings = settings
        self.logger = logger

    def enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild(guild_id, "server_guide.enabled", True))

    @staticmethod
    def _module_key_from_path(path: str) -> str:
        parts = str(path or "").split(".")
        try:
            i = parts.index("modules")
            return str(parts[i + 1])
        except Exception:
            return "misc"

    @staticmethod
    def _pretty_title(key: str) -> str:
        return str(key).replace("_", " ").strip().title()

    def _walk_app(self, node: Any, prefix: str = "") -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if isinstance(node, app_commands.Group):
            full = f"{prefix} {node.name}".strip()
            if node.description:
                out.append((f"/{full}", str(node.description)))
            for child in node.commands:
                out.extend(self._walk_app(child, full))
            return out
        if isinstance(node, app_commands.Command):
            full = f"{prefix} {node.name}".strip()
            out.append((f"/{full}", str(node.description or "")))
            return out
        return out

    @staticmethod
    def _prefix_usage(cmd: commands.Command) -> str:
        name = str(cmd.qualified_name)
        sig = str(cmd.signature or "").strip()
        return f"!{name}{(' ' + sig) if sig else ''}"

    def collect_module_guides(self) -> list[ModuleGuide]:
        by_module: dict[str, list[str]] = {}

        for cog in self.bot.cogs.values():
            key = self._module_key_from_path(getattr(cog, "__module__", ""))
            if key in {"logs"}:
                continue
            lines = by_module.setdefault(key, [])

            try:
                app_nodes = cog.get_app_commands()
            except Exception:
                app_nodes = []
            for node in app_nodes:
                for cmd_path, desc in self._walk_app(node):
                    lines.append(f"• `{cmd_path}`{(' — ' + desc) if desc else ''}")

            try:
                prefix_cmds = cog.get_commands()
            except Exception:
                prefix_cmds = []
            for cmd in prefix_cmds:
                if cmd.hidden:
                    continue
                usage = self._prefix_usage(cmd)
                desc = str(cmd.help or cmd.brief or "").strip()
                lines.append(f"• `{usage}`{(' — ' + desc) if desc else ''}")

        guides: list[ModuleGuide] = []
        for key, lines in by_module.items():
            cleaned = []
            seen = set()
            for line in lines:
                if line in seen:
                    continue
                seen.add(line)
                cleaned.append(line)
            if not cleaned:
                continue
            guides.append(ModuleGuide(key=key, title=self._pretty_title(key), commands=cleaned))

        guides.sort(key=lambda g: g.title.lower())
        return guides

    async def _create_thread(self, target: discord.abc.GuildChannel, name: str, starter_text: str) -> discord.Thread | None:
        if isinstance(target, discord.ForumChannel):
            try:
                result = await target.create_thread(name=name[:100], content=starter_text[:1900])
                thread = getattr(result, "thread", None)
                return thread or result
            except Exception:
                return None

        if isinstance(target, discord.TextChannel):
            try:
                msg = await target.send(starter_text[:1900])
                thread = await msg.create_thread(name=name[:100], auto_archive_duration=10080)
                return thread
            except Exception:
                return None

        return None

    async def build(self, guild: discord.Guild, target: discord.TextChannel | discord.ForumChannel | None = None) -> tuple[bool, str]:
        if not self.enabled(guild.id):
            return False, "Server-Guide ist deaktiviert."

        channel = target
        if channel is None:
            cid = int(self.settings.get_guild(guild.id, "server_guide.channel_id", 0) or 0)
            if cid:
                channel = guild.get_channel(cid)
                if channel is None:
                    try:
                        channel = await guild.fetch_channel(cid)
                    except Exception:
                        channel = None
        if channel is None:
            return False, "Kein Guide-Channel gesetzt. Bitte Channel angeben oder `server_guide.channel_id` konfigurieren."

        guides = self.collect_module_guides()
        if not guides:
            return False, "Keine Module/Commands gefunden."

        hub = await self._create_thread(channel, "📘 Server Guide • Übersicht", "Hier entsteht dein kompletter Modul-Guide.")
        if not hub:
            return False, "Guide-Hub-Thread konnte nicht erstellt werden."

        try:
            await hub.send(embed=build_hub_embed(self.settings, guild, len(guides)))
        except Exception:
            pass

        created = 0
        for g in guides:
            thread_name = f"📚 {g.title} • Guide"
            th = await self._create_thread(channel, thread_name, f"Guide für Modul: **{g.title}**")
            if not th:
                continue
            created += 1
            try:
                await th.send(embed=build_module_embed(self.settings, guild, g.title, g.key, g.commands))
            except Exception:
                pass
            try:
                await hub.send(f"• {th.mention} — **{g.title}**")
            except Exception:
                pass

        return True, f"Guide erstellt. Hub: {hub.mention} | Modul-Threads: **{created}/{len(guides)}**"

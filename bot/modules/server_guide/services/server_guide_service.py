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

    def _exclude_modules(self, guild_id: int) -> set[str]:
        base = {
            "backup",
            "logs",
        }
        raw = self.settings.get_guild(guild_id, "server_guide.exclude_modules", []) or []
        for item in raw:
            s = str(item or "").strip().lower()
            if s:
                base.add(s)
        return base

    def _exclude_keywords(self, guild_id: int) -> list[str]:
        raw = self.settings.get_guild(
            guild_id,
            "server_guide.exclude_command_keywords",
            [
                "admin",
                "setup",
                "sync",
                "rescan",
                "debug",
                "backup",
                "build",
                "panel-senden",
                "mass-add",
                "grant",
                "revoke",
            ],
        ) or []
        out: list[str] = []
        for item in raw:
            s = str(item or "").strip().lower()
            if s:
                out.append(s)
        return out

    def _is_admin_command(self, text: str, keywords: list[str]) -> bool:
        low = str(text or "").lower()
        return any(k in low for k in keywords)

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

    def collect_module_guides(self, guild_id: int) -> list[ModuleGuide]:
        by_module: dict[str, list[str]] = {}
        excluded_modules = self._exclude_modules(guild_id)
        excluded_keywords = self._exclude_keywords(guild_id)

        for cog in self.bot.cogs.values():
            key = self._module_key_from_path(getattr(cog, "__module__", ""))
            if key in excluded_modules:
                continue
            lines = by_module.setdefault(key, [])

            try:
                app_nodes = cog.get_app_commands()
            except Exception:
                app_nodes = []
            for node in app_nodes:
                for cmd_path, desc in self._walk_app(node):
                    if self._is_admin_command(cmd_path, excluded_keywords):
                        continue
                    lines.append(f"• `{cmd_path}`{(' — ' + desc) if desc else ''}")

            try:
                prefix_cmds = cog.get_commands()
            except Exception:
                prefix_cmds = []
            for cmd in prefix_cmds:
                if cmd.hidden:
                    continue
                usage = self._prefix_usage(cmd)
                if self._is_admin_command(usage, excluded_keywords):
                    continue
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

    async def _create_post(self, forum: discord.ForumChannel, name: str, starter_text: str) -> discord.Thread | None:
        try:
            result = await forum.create_thread(name=name[:100], content=starter_text[:1900])
            thread = getattr(result, "thread", None)
            return thread or result
        except Exception:
            return None

    async def build(self, guild: discord.Guild, target: discord.ForumChannel | None = None) -> tuple[bool, str]:
        if not self.enabled(guild.id):
            return False, "Server-Guide ist deaktiviert."

        forum = target
        if forum is None:
            cid = int(self.settings.get_guild(guild.id, "server_guide.forum_channel_id", 0) or 0)
            if not cid:
                cid = int(self.settings.get_guild(guild.id, "server_guide.channel_id", 0) or 0)
            if cid:
                forum = guild.get_channel(cid)
                if forum is None:
                    try:
                        forum = await guild.fetch_channel(cid)
                    except Exception:
                        forum = None
        if forum is None:
            return False, "Kein Guide-Forum gesetzt. Bitte Forum-Channel angeben oder `server_guide.forum_channel_id` konfigurieren."
        if not isinstance(forum, discord.ForumChannel):
            return False, "Der Guide-Kanal muss ein Forum sein."

        guides = self.collect_module_guides(guild.id)
        if not guides:
            return False, "Keine Module/Commands gefunden."

        hub = await self._create_post(forum, "📘 Server Guide • Übersicht", "Hier entsteht dein kompletter Modul-Guide.")
        if not hub:
            return False, "Guide-Hub-Post konnte nicht erstellt werden."

        try:
            await hub.send(embed=build_hub_embed(self.settings, guild, len(guides)))
        except Exception:
            pass

        created = 0
        for g in guides:
            thread_name = f"📚 {g.title} • Guide"
            th = await self._create_post(forum, thread_name, f"Guide für Modul: **{g.title}**")
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

        return True, f"Guide erstellt. Hub: {hub.mention} | Modul-Posts: **{created}/{len(guides)}**"

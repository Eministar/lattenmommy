import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.cogs.dm_listener import DMListener
from bot.cogs.forum_listener import ForumListener
from bot.cogs.ticket_commands import TicketCommands

from bot.cogs.moderation_commands import ModerationCommands
from bot.cogs.modlog_listener import ModLogListener
from bot.cogs.channel_role_log_listener import ChannelRoleLogListener

from bot.core.presence import PresenceRotator
from bot.logs.forum_log_service import ForumLogService
from bot.utils.mod_formatting import build_bot_error_embed


class StarryBot(commands.Bot):
    def __init__(self, settings, db, logger):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        intents.messages = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents
        )

        self.settings = settings
        self.db = db
        self.logger = logger

        self.forum_logs = ForumLogService(self, self.settings, self.db)
        self._boot_done = False

        self.reload_settings_loop.start()

    async def setup_hook(self):
        await self.add_cog(DMListener(self))
        await self.add_cog(ForumListener(self))
        await self.add_cog(TicketCommands(self))

        await self.add_cog(ModerationCommands(self))
        await self.add_cog(ModLogListener(self))
        await self.add_cog(ChannelRoleLogListener(self))

        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self._handle_app_command_error(interaction, error)

        guild_id = self.settings.get_int("bot.guild_id")
        if guild_id:
            guild = discord.Object(id=guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            self.presence = PresenceRotator(self, self.db, interval_seconds=20)
            self.presence.start()
        else:
            await self.tree.sync()

    @tasks.loop(seconds=2.0)
    async def reload_settings_loop(self):
        changed = await self.settings.reload_if_changed()
        if changed:
            await self.logger.emit_system("settings_reloaded", {"source": "dashboard_override"})

    @reload_settings_loop.error
    async def reload_settings_loop_error(self, error: Exception):
        await self._emit_bot_error("reload_settings_loop", error, extra=None)

    async def on_ready(self):
        if self._boot_done:
            return
        self._boot_done = True
        await self.forum_logs.start()

    async def on_error(self, event_method: str, *args, **kwargs):
        import sys
        err = sys.exc_info()[1]
        if err:
            await self._emit_bot_error(f"event:{event_method}", err, extra={"args": len(args)})

    async def _handle_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        extra = {
            "user": f"{interaction.user} ({interaction.user.id})" if interaction.user else "—",
            "guild": f"{interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "—",
            "channel": f"{getattr(interaction.channel,'id',0)}",
            "command": getattr(getattr(interaction, "command", None), "name", None) or "unknown",
        }
        await self._emit_bot_error("app_command_error", error, extra=extra)

        try:
            if interaction.response.is_done():
                await interaction.followup.send("Da ist was gecrashed. Wurde geloggt.", ephemeral=True)
            else:
                await interaction.response.send_message("Da ist was gecrashed. Wurde geloggt.", ephemeral=True)
        except Exception:
            pass

    async def _emit_bot_error(self, where: str, error: BaseException, extra: dict | None):
        guild_id = self.settings.get_int("bot.guild_id")
        guild = self.get_guild(guild_id) if guild_id else None
        emb = build_bot_error_embed(self.settings, guild, where, error, extra=extra)

        try:
            if self.forum_logs:
                await self.forum_logs.emit("bot_errors", emb)
        except Exception:
            pass

        try:
            await self.logger.emit_system("bot_error", {"where": where, "type": type(error).__name__, "msg": str(error)})
        except Exception:
            pass

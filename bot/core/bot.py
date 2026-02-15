import discord
from datetime import datetime, timezone
from discord import app_commands
from discord.ext import commands, tasks

from bot.modules.tickets.cogs.ticket_dm_listener import TicketDMListener
from bot.modules.tickets.cogs.ticket_forum_listener import TicketForumListener
from bot.modules.tickets.cogs.ticket_commands import TicketCommands
from bot.modules.tickets.cogs.text_snippets import TextSnippetsCommands
from bot.modules.tickets.services.ticket_service import TicketService
from bot.modules.tickets.views.summary_view import SummaryView
from bot.modules.tickets.views.rating_view import RatingButton
from bot.modules.user_stats.cogs.user_stats_listener import UserStatsListener
from bot.modules.user_stats.cogs.user_stats_commands import UserStatsCommands
from bot.modules.user_stats.services.user_stats_service import UserStatsService
from bot.modules.backup.cogs.backup_commands import BackupCommands
from bot.modules.backup.services.backup_service import BackupService
from bot.modules.birthdays.cogs.birthday_listener import BirthdayListener
from bot.modules.birthdays.cogs.birthday_commands import BirthdayCommands
from bot.modules.birthdays.services.birthday_service import BirthdayService
from bot.modules.roles.cogs.roles_commands import RolesCommands
from bot.modules.roles.views.roles_info_panel import RolesInfoPanelView
from bot.modules.custom_roles.services.custom_role_service import CustomRoleService
from bot.modules.custom_roles.cogs.custom_role_commands import CustomRoleCommands
from bot.modules.server_guide.services.server_guide_service import ServerGuideService
from bot.modules.server_guide.cogs.server_guide_commands import ServerGuideCommands
from bot.modules.reminder_afk.services.reminder_afk_service import ReminderAfkService
from bot.modules.reminder_afk.cogs.reminder_afk_commands import ReminderAfkCommands
from bot.modules.flags.services.flag_quiz_service import FlagQuizService
from bot.modules.flags.cogs.flag_commands import FlagCommands
from bot.modules.flags.cogs.flag_listener import FlagListener
from bot.modules.giveaways.cogs.giveaway_commands import GiveawayCommands
from bot.modules.giveaways.cogs.giveaway_listener import GiveawayListener
from bot.modules.giveaways.services.giveaway_service import GiveawayService
from bot.modules.polls.cogs.poll_commands import PollCommands
from bot.modules.polls.services.poll_service import PollService
from bot.modules.news.cogs.news_commands import NewsCommands
from bot.modules.news.services.news_service import NewsService
from bot.modules.placeholders.services.placeholder_service import PlaceholderService
from bot.modules.welcome.cogs.welcome_listener import WelcomeListener
from bot.modules.welcome.services.welcome_service import WelcomeService
from bot.modules.ai.cogs.mention_ai_listener import MentionAIListener
from bot.modules.ai.cogs.ai_commands import AICommands
from bot.modules.ai.services.deepseek_service import DeepSeekService
from bot.modules.counting.cogs.counting_listener import CountingListener
from bot.modules.counting.cogs.counting_commands import CountingCommands
from bot.modules.counting.services.counting_service import CountingService
from bot.modules.wort_zum_sonntag.cogs.wort_commands import WortCommands
from bot.modules.wort_zum_sonntag.services.wort_service import WortZumSonntagService
from bot.modules.wort_zum_sonntag.views.panel import WortPanelView
from bot.modules.wort_zum_sonntag.views.info import WortInfoView

from bot.modules.moderation.cogs.moderation_commands import ModerationCommands  
from bot.modules.logs.cogs.modlog_listener import ModLogListener
from bot.modules.logs.cogs.channel_role_log_listener import ChannelRoleLogListener
from bot.modules.applications.cogs.application_commands import ApplicationCommands
from bot.modules.applications.services.application_service import ApplicationService
from bot.modules.applications.views.application_panel import ApplicationPanelView
from bot.modules.applications.views.application_decision import ApplicationDecisionButton
from bot.modules.tempvoice.cogs.tempvoice_listener import TempVoiceListener
from bot.modules.tempvoice.cogs.tempvoice_commands import TempVoiceCommands
from bot.modules.tempvoice.services.tempvoice_service import TempVoiceService
from bot.modules.tickets.views.support_panel import SupportPanelView
from bot.modules.fun.cogs.fun_commands import FunCommands
from bot.modules.ping.cogs.ping_commands import PingCommands
from bot.modules.suggestions.services.suggestion_service import SuggestionService
from bot.modules.suggestions.cogs.suggestion_commands import SuggestionCommands
from bot.modules.suggestions.cogs.suggestion_forum_listener import SuggestionForumListener
from bot.modules.suggestions.views.suggestion_panel import SuggestionPanelView
from bot.modules.seelsorge.services.seelsorge_service import SeelsorgeService
from bot.modules.seelsorge.cogs.seelsorge_commands import SeelsorgeCommands
from bot.modules.seelsorge.cogs.seelsorge_listener import SeelsorgeListener
from bot.modules.seelsorge.views.panel import SeelsorgePanelView
from bot.modules.beichte.services.beichte_service import BeichteService
from bot.modules.beichte.cogs.beichte_commands import BeichteCommands
from bot.modules.beichte.cogs.beichte_listener import BeichteListener
from bot.modules.beichte.views.info import BeichteInfoView
from bot.modules.invites.services.invite_service import InviteService
from bot.modules.invites.cogs.invite_listener import InviteListener
from bot.modules.parlament.services.parlament_service import ParliamentService
from bot.modules.parlament.cogs.parlament_commands import ParliamentCommands
from bot.modules.bot_status.services.bot_status_service import BotStatusService

from bot.core.presence import PresenceRotator
from bot.modules.logs.forum_log_service import ForumLogService
from bot.modules.logs.formatting.log_embeds import build_bot_error_embed


class StarryBot(commands.Bot):
    def __init__(self, settings, db, logger):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.presences = True
        intents.guilds = True
        intents.messages = True
        intents.dm_messages = True
        intents.guild_messages = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents
        )

        self.settings = settings
        self.db = db
        self.logger = logger

        self.ticket_service = TicketService(self, self.settings, self.db, self.logger)
        self.user_stats_service = UserStatsService(self, self.settings, self.db, self.logger)
        self.backup_service = BackupService(self, self.settings, self.db, self.logger)
        self.birthday_service = BirthdayService(self, self.settings, self.db, self.logger)
        self.giveaway_service = GiveawayService(self, self.settings, self.db, self.logger)
        self.poll_service = PollService(self, self.settings, self.db, self.logger)
        self.tempvoice_service = TempVoiceService(self, self.settings, self.db, self.logger)
        self.news_service = NewsService(self, self.settings, self.db, self.logger)
        self.application_service = ApplicationService(self, self.settings, self.db, self.logger)
        self.placeholder_service = PlaceholderService(self, self.settings, self.db, self.logger)
        self.welcome_service = WelcomeService(self, self.settings, self.db, self.logger)
        self.wzs_service = WortZumSonntagService(self, self.settings, self.db, self.logger)
        self.deepseek_service = DeepSeekService(self, self.settings, self.logger)
        self.counting_service = CountingService(self, self.settings, self.db, self.logger)
        self.suggestion_service = SuggestionService(self, self.settings, self.db, self.logger)
        self.seelsorge_service = SeelsorgeService(self, self.settings, self.db, self.logger)
        self.beichte_service = BeichteService(self, self.settings, self.db, self.logger)
        self.parlament_service = ParliamentService(self, self.settings, self.db, self.logger)
        self.invite_service = InviteService(self, self.settings, self.db, self.logger)
        self.bot_status_service = BotStatusService(self, self.settings, self.logger)
        self.flag_quiz_service = FlagQuizService(self, self.settings, self.db, self.logger)
        self.custom_role_service = CustomRoleService(self, self.settings, self.db, self.logger)
        self.server_guide_service = ServerGuideService(self, self.settings, self.logger)
        self.reminder_afk_service = ReminderAfkService(self, self.settings, self.db, self.logger)

        self.forum_logs = ForumLogService(self, self.settings, self.db)
        self._boot_done = False

        self.reload_settings_loop.start()
        self.ticket_automation_loop.start()
        self.backup_autosave_loop.start()
        self.birthday_loop.start()
        self.giveaway_loop.start()
        self.news_loop.start()
        self.placeholder_loop.start()
        self.parlament_loop.start()
        self.reminder_loop.start()

    async def setup_hook(self):
        await self.add_cog(TicketDMListener(self))
        await self.add_cog(TicketForumListener(self))
        await self.add_cog(TicketCommands(self))
        await self.add_cog(TextSnippetsCommands(self))
        await self.add_cog(UserStatsListener(self))
        await self.add_cog(UserStatsCommands(self))
        await self.add_cog(BackupCommands(self))
        await self.add_cog(BirthdayListener(self))
        await self.add_cog(BirthdayCommands(self))
        await self.add_cog(RolesCommands(self))
        await self.add_cog(CustomRoleCommands(self))
        await self.add_cog(ServerGuideCommands(self))
        await self.add_cog(ReminderAfkCommands(self))
        await self.add_cog(FlagListener(self))
        await self.add_cog(FlagCommands(self))
        await self.add_cog(GiveawayCommands(self))
        await self.add_cog(GiveawayListener(self))
        await self.add_cog(PollCommands(self))
        await self.add_cog(TempVoiceListener(self))
        await self.add_cog(TempVoiceCommands(self))
        await self.add_cog(NewsCommands(self))
        await self.add_cog(WelcomeListener(self))
        await self.add_cog(MentionAIListener(self))
        await self.add_cog(AICommands(self))
        await self.add_cog(CountingListener(self))
        await self.add_cog(CountingCommands(self))
        await self.add_cog(WortCommands(self))

        await self.add_cog(FunCommands(self))
        await self.add_cog(PingCommands(self))
        await self.add_cog(SuggestionForumListener(self))
        await self.add_cog(SuggestionCommands(self))
        await self.add_cog(SeelsorgeListener(self))
        await self.add_cog(SeelsorgeCommands(self))
        await self.add_cog(BeichteListener(self))
        await self.add_cog(BeichteCommands(self))
        await self.add_cog(InviteListener(self))
        await self.add_cog(ParliamentCommands(self))
        await self.add_cog(ModerationCommands(self))
        await self.add_cog(ModLogListener(self))
        await self.add_cog(ChannelRoleLogListener(self))
        await self.add_cog(ApplicationCommands(self))

        self.add_view(SummaryView(self.ticket_service, ticket_id=0, status="open"))
        self.add_dynamic_items(RatingButton)
        self.add_dynamic_items(ApplicationDecisionButton)
        self.add_view(ApplicationPanelView(self.settings))
        self.add_view(SupportPanelView(self.settings))
        self.add_view(RolesInfoPanelView(self.settings))
        self.add_view(SuggestionPanelView(self.settings))
        self.add_view(WortPanelView(self.wzs_service))
        self.add_view(WortInfoView(self.wzs_service))
        self.add_view(SeelsorgePanelView(self.seelsorge_service))
        self.add_view(BeichteInfoView(self.beichte_service))

        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            await self._handle_app_command_error(interaction, error)

        await self.tree.sync()
        self.presence = PresenceRotator(self, self.db, interval_seconds=20)
        self.presence.start()

    @tasks.loop(seconds=2.0)
    async def reload_settings_loop(self):
        changed = await self.settings.reload_if_changed()
        if changed:
            await self.logger.emit_system("settings_reloaded", {"source": "dashboard_override"})

    @tasks.loop(seconds=60.0)
    async def ticket_automation_loop(self):
        try:
            await self.ticket_service.run_automation()
        except Exception:
            pass

    @tasks.loop(seconds=600.0)
    async def backup_autosave_loop(self):
        now = datetime.now(timezone.utc)
        for guild in list(self.guilds):
            if not self.settings.get_guild_bool(guild.id, "backup.enabled", True):
                continue
            if not self.settings.get_guild_bool(guild.id, "backup.auto_save_enabled", False):
                continue
            interval_hours = float(self.settings.get_guild(guild.id, "backup.auto_save_interval_hours", 24) or 24)
            last = self.settings.get_guild(guild.id, "backup.last_auto_save_at", None)
            if last:
                try:
                    last_dt = datetime.fromisoformat(str(last))
                except Exception:
                    last_dt = None
                if last_dt and (now - last_dt).total_seconds() < interval_hours * 3600:
                    continue
            name = self.settings.get_guild(guild.id, "backup.auto_save_name", "autosave")
            try:
                await self.backup_service.create_backup(guild, name=f"{name}-{now.strftime('%Y%m%d-%H%M')}")
                await self.settings.set_guild_override(self.db, guild.id, "backup.last_auto_save_at", now.isoformat())
            except Exception:
                pass

    @tasks.loop(seconds=30.0)
    async def birthday_loop(self):
        try:
            await self.birthday_service.tick_midnight()
        except Exception:
            pass

    @tasks.loop(seconds=30.0)
    async def giveaway_loop(self):
        try:
            await self.giveaway_service.tick()
        except Exception:
            pass

    @tasks.loop(seconds=60.0)
    async def news_loop(self):
        try:
            await self.news_service.tick()
        except Exception:
            pass

    @tasks.loop(seconds=60.0)
    async def placeholder_loop(self):
        try:
            if not self.placeholder_service:
                return
            for guild in list(self.guilds):
                await self.placeholder_service.tick(guild)
        except Exception:
            pass

    @tasks.loop(seconds=60.0)
    async def parlament_loop(self):
        try:
            if not self.parlament_service:
                return
            await self.parlament_service.refresh_all_panels()
        except Exception:
            pass

    @tasks.loop(seconds=20.0)
    async def reminder_loop(self):
        try:
            if self.reminder_afk_service:
                await self.reminder_afk_service.tick()
        except Exception:
            pass

    @reload_settings_loop.error
    async def reload_settings_loop_error(self, error: Exception):
            await self._emit_bot_error("reload_settings_loop", error, extra=None, guild=None)

    @ticket_automation_loop.error
    async def ticket_automation_loop_error(self, error: Exception):
            await self._emit_bot_error("ticket_automation_loop", error, extra=None, guild=None)

    @backup_autosave_loop.error
    async def backup_autosave_loop_error(self, error: Exception):
            await self._emit_bot_error("backup_autosave_loop", error, extra=None, guild=None)

    @birthday_loop.error
    async def birthday_loop_error(self, error: Exception):
            await self._emit_bot_error("birthday_loop", error, extra=None, guild=None)

    @giveaway_loop.error
    async def giveaway_loop_error(self, error: Exception):
            await self._emit_bot_error("giveaway_loop", error, extra=None, guild=None)

    @news_loop.error
    async def news_loop_error(self, error: Exception):
            await self._emit_bot_error("news_loop", error, extra=None, guild=None)

    @placeholder_loop.error
    async def placeholder_loop_error(self, error: Exception):
            await self._emit_bot_error("placeholder_loop", error, extra=None, guild=None)

    @parlament_loop.error
    async def parlament_loop_error(self, error: Exception):
            await self._emit_bot_error("parlament_loop", error, extra=None, guild=None)

    @reminder_loop.error
    async def reminder_loop_error(self, error: Exception):
            await self._emit_bot_error("reminder_loop", error, extra=None, guild=None)


    async def on_ready(self):
        if self._boot_done:
            return
        self._boot_done = True
        try:
            print(f"[OK] Discord verbunden als {self.user} ({self.user.id})")
        except Exception:
            pass
        await self.forum_logs.start()
        for guild in list(self.guilds):
            if self.user_stats_service:
                try:
                    await self.user_stats_service.seed_voice_sessions(guild)
                except Exception:
                    pass
            if self.user_stats_service:
                try:
                    await self.user_stats_service.ensure_roles(guild)
                except Exception:
                    pass
            if self.user_stats_service:
                try:
                    await self.user_stats_service.seed_boosters(guild)
                except Exception:
                    pass
            if self.birthday_service:
                try:
                    await self.birthday_service.ensure_roles(guild)
                except Exception:
                    pass
            if self.counting_service:
                try:
                    await self.counting_service.sync_guild(guild)
                except Exception:
                    pass
        if self.poll_service:
            try:
                await self.poll_service.restore_views()
            except Exception:
                pass
        if self.parlament_service:
            try:
                await self.parlament_service.restore_views()
            except Exception:
                pass
        if self.bot_status_service:
            try:
                await self.bot_status_service.send_start()
            except Exception:
                pass

    async def on_error(self, event_method: str, *args, **kwargs):
        import sys
        err = sys.exc_info()[1]
        if err:
            await self._emit_bot_error(f"event:{event_method}", err, extra={"args": len(args)}, guild=None)

    async def _handle_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        extra = {
            "user": f"{interaction.user} ({interaction.user.id})" if interaction.user else "—",
            "guild": f"{interaction.guild.name} ({interaction.guild.id})" if interaction.guild else "—",
            "channel": f"{getattr(interaction.channel,'id',0)}",
            "command": getattr(getattr(interaction, "command", None), "name", None) or "unknown",
        }
        await self._emit_bot_error("app_command_error", error, extra=extra, guild=interaction.guild)

        try:
            if interaction.response.is_done():
                await interaction.followup.send("Da ist was gecrashed. Wurde geloggt.", ephemeral=True)
            else:
                await interaction.response.send_message("Da ist was gecrashed. Wurde geloggt.", ephemeral=True)
        except Exception:
            pass

    async def _emit_bot_error(self, where: str, error: BaseException, extra: dict | None, guild: discord.Guild | None):
        emb = build_bot_error_embed(self.settings, guild, where, error, extra=extra)

        try:
            if self.forum_logs and guild:
                await self.forum_logs.emit(guild, "bot_errors", emb)
        except Exception:
            pass

    async def close(self):
        if self.bot_status_service:
            try:
                await self.bot_status_service.send_stop()
            except Exception:
                pass
        await super().close()

        try:
            await self.logger.emit_system("bot_error", {"where": where, "type": type(error).__name__, "msg": str(error)})
        except Exception:
            pass

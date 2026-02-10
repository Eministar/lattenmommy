import random
import discord
from bot.utils.assets import Banners


class WelcomeService:
    def __init__(self, bot: discord.Client, settings, db, logger):
        self.bot = bot
        self.settings = settings
        self.db = db
        self.logger = logger

    def _enabled(self, guild_id: int) -> bool:
        return bool(self.settings.get_guild_bool(guild_id, "welcome.enabled", True))

    def _channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "welcome.channel_id", 0) or 0)

    def _small_text_channel_id(self, guild_id: int) -> int:
        cid = int(self.settings.get_guild_int(guild_id, "welcome.small_text_channel_id", 0) or 0)
        return cid or self._channel_id(guild_id)

    def _embed_channel_id(self, guild_id: int) -> int:
        cid = int(self.settings.get_guild_int(guild_id, "welcome.embed_channel_id", 0) or 0)
        return cid or self._channel_id(guild_id)

    def _small_text(self, guild_id: int) -> str:
        return str(self.settings.get_guild(guild_id, "welcome.small_text", "👋 Willkommen bei uns,") or "").strip()

    def _leave_channel_id(self, guild_id: int) -> int:
        return int(self.settings.get_guild_int(guild_id, "welcome.leave_channel_id", 0) or 0)

    def _leave_text(self, guild_id: int) -> str:
        return str(self.settings.get_guild(guild_id, "welcome.leave_text", "👋 {user} hat uns verlassen.") or "").strip()

    def _presets(self, guild_id: int) -> list[str]:
        return self.settings.get_guild(guild_id, "welcome.presets", []) or []

    def _role_ids(self, guild_id: int) -> list[int]:
        raw = self.settings.get_guild(guild_id, "welcome.role_ids", []) or []
        out = []
        for v in raw:
            try:
                out.append(int(v))
            except Exception:
                pass
        return out

    def _embed_color(self, member: discord.Member | None) -> int:
        try:
            if member and int(member.color.value) != 0:
                return int(member.color.value)
        except Exception:
            pass
        v = str(self.settings.get_guild(member.guild.id, "design.accent_color", "#B16B91") or "").replace("#", "").strip()
        try:
            return int(v, 16)
        except Exception:
            return 0xB16B91

    def _add_banner(self, container: discord.ui.Container):
        try:
            gallery = discord.ui.MediaGallery()
            gallery.add_item(media=Banners.WELCOME)
            container.add_item(gallery)
            container.add_item(discord.ui.Separator())
        except Exception:
            pass

    def _build_welcome_view(self, member: discord.Member, preset: str, member_count: int) -> discord.ui.LayoutView:
        guild = member.guild
        header = "**👋 𑁉 WILLKOMMEN**"
        desc = (
            f"{preset}\n\n"
            f"┏`👤` - User: {member.mention}\n"
            f"┣`🏠` - Server: **{guild.name}**\n"
            f"┗`👥` - Members: **{member_count}**"
        )
        container = discord.ui.Container(accent_colour=self._embed_color(member))
        self._add_banner(container)
        container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)
        return view

    async def _resolve_channel(self, guild: discord.Guild, channel_id: int) -> discord.abc.Messageable | None:
        if not channel_id:
            return None
        ch = guild.get_channel(int(channel_id))
        if not ch:
            try:
                ch = await self.bot.fetch_channel(int(channel_id))
            except Exception:
                ch = None
        if not ch or not isinstance(ch, discord.abc.Messageable):
            return None
        return ch

    async def handle_member_join(self, member: discord.Member):
        guild = member.guild
        if not guild or not self._enabled(guild.id):
            return
        if member.bot:
            return

        small_ch = await self._resolve_channel(guild, self._small_text_channel_id(guild.id))
        embed_ch = await self._resolve_channel(guild, self._embed_channel_id(guild.id))
        if not small_ch and not embed_ch:
            return

        presets = self._presets(guild.id)
        preset = random.choice(presets) if presets else "Schön, dass du da bist!"
        member_count = guild.member_count or len(guild.members)

        small_text = self._small_text(guild.id)
        if small_text and small_ch:
            try:
                await small_ch.send(f"{small_text} {member.mention}")
            except Exception:
                pass
        if embed_ch:
            try:
                view = self._build_welcome_view(member, preset, member_count)
                await embed_ch.send(view=view)
            except Exception:
                pass

        role_ids = self._role_ids(guild.id)
        if role_ids:
            roles = []
            for rid in role_ids:
                role = guild.get_role(int(rid))
                if role and role not in member.roles:
                    roles.append(role)
            if roles:
                try:
                    await member.add_roles(*roles, reason="Welcome roles")
                except Exception:
                    pass

    async def handle_member_leave(self, member: discord.Member):
        guild = member.guild
        if not guild or not self._enabled(guild.id):
            return
        if member.bot:
            return

        ch = await self._resolve_channel(guild, self._leave_channel_id(guild.id))
        if not ch:
            return

        text = self._leave_text(guild.id)
        if not text:
            return
        text = text.replace("{user}", member.mention).replace("{server}", guild.name)
        try:
            await ch.send(text)
        except Exception:
            pass

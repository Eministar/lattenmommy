import discord

def is_staff(settings, member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    support_role = settings.get_int("bot.support_role_id")
    staff_roles = settings.get("bot.staff_role_ids", []) or []
    allowed = set([support_role] + [int(x) for x in staff_roles if str(x).isdigit()])
    return any(r.id in allowed for r in member.roles)

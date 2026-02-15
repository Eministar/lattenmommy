import discord

def is_staff(settings, member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    support_role = int(settings.get_guild_int(member.guild.id, "bot.support_role_id") or 0)
    raw_staff_roles = settings.get_guild(member.guild.id, "bot.staff_role_ids", []) or []

    if isinstance(raw_staff_roles, (int, str)):
        staff_roles = [raw_staff_roles]
    else:
        try:
            staff_roles = list(raw_staff_roles)
        except Exception:
            staff_roles = []

    allowed = set()
    if support_role > 0:
        allowed.add(support_role)
    for x in staff_roles:
        try:
            rid = int(x)
        except Exception:
            continue
        if rid > 0:
            allowed.add(rid)
    return any(r.id in allowed for r in member.roles)

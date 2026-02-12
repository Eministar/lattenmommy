ASSET_BASE_URL = "https://bkt-info.org/bot/assets/"


def asset_url(path: str) -> str:
    cleaned = str(path or "").lstrip("/")
    return f"{ASSET_BASE_URL}{cleaned}"


class Banners:
    ACHIEVEMENT = asset_url("achievement-banner.png")
    ACHIEVEMENT_COMPLETE = asset_url("achievement-complete-banner.png")
    APPLICATION = asset_url("application-banner.png")
    BEICHTE = asset_url("beichten-banner.png")
    BOT_ERROR = asset_url("bot-error-banner.png")
    BOT_BANNER = asset_url("bot-banner.png")
    BIRTHDAY_BANNER = asset_url("birthday-banner.png")
    COUNTING = asset_url("counting-banner.png")
    ELECTION = asset_url("election-banner.png")
    GIVEAWAY = asset_url("giveaway-banner.png")
    INVITE = asset_url("invite-banner.png")
    PARLIAMENT = asset_url("parliament-banner.png")
    POLL = asset_url("poll-banner.png")
    SEELSORGE = asset_url("seelsorge-banner.png")
    SUPPORT = asset_url("support-banner.png")
    TEMPVOICE = asset_url("tempvoice-banner.png")
    WELCOME = asset_url("welcome-banner.png")

    TICKETS_ANSWER = asset_url("tickets/tickets-answer-banner.png")
    TICKETS_CLAIM = asset_url("tickets/tickets-claim-banner.png")
    TICKETS_CLOSED = asset_url("tickets/tickets-closed-banner.png")
    TICKETS_OPENED = asset_url("tickets/tickets-opened-banner.png")
    TICKETS_STAFF = asset_url("tickets/tickets-staff-banner.png")

    WZM_ACCEPTED = asset_url("wzm/wzm-accepted-banner.png")
    WZM_BANNER = asset_url("wzm/wzm-banner.png")
    WZM_DENIED = asset_url("wzm/wzm-denied-banner.png")
    WZM_WAITING = asset_url("wzm/wzm-waiting-banner.png")

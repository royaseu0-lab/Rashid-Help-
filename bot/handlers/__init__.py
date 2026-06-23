from . import antispam, general, moderation, owner_panel, replies, welcome

routers = [
    owner_panel.router,
    general.router,
    moderation.router,
    welcome.router,
    replies.router,
    antispam.router,
]

from . import admin_panel, antispam, general, moderation, replies, welcome

routers = [
    admin_panel.router,
    general.router,
    moderation.router,
    welcome.router,
    replies.router,
    antispam.router,
]

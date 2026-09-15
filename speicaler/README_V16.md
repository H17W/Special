# Special V16

Final integration build focused on:
- Exact reply-based range delete in private chats, groups, and channels where the account can delete other users' messages.
- Reply-based mute/unmute in private chats, groups, and channels.
- Human-only private contact sync and historical private-message import with one database row per physical Telegram message.
- Paginated private contacts plus search by display name, @username, or Telegram ID.
- Private-message edit monitoring with before/after text, sender identity, and direct profile button; bot messages are ignored.
- AI responses from the user account in private chats, groups, and channels using `سبيشل + السؤال` or an optional custom trigger.
- AI responses in the management bot where Bot API visibility/permissions allow the bot to receive and answer the message.
- AI enable/disable switch, custom trigger, and AI question/answer log in the management bot.
- New `/start` notifications to the owner even when the visitor is unauthorized.
- Automatic Telethon reconnect watchdog and runtime refresh.
- Broadcast targets restricted to real human private contacts; bots, groups, and channels are excluded.

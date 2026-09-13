# Special V17

- Exact `/بداية الحذف` + `/نهاية الحذف` using the replied-to message as the boundaries.
- Private deletion notifications audited chat-by-chat to avoid false positives from Telegram delete updates without peer context.
- Bot-access log with name, username, ID, status and history.
- Configurable mimic settings for name, photo, bio, similar username, and a safe stored location toggle.
- `ايقاف البوت` pauses Bot API command handling only; user-account automation, private monitoring, mute/delete and temporary media handling remain active. `تفعيل` resumes the bot.
- All existing V16 files/features retained.

## Runtime notes

Private deletion notifications are produced by per-chat verification rather than trusting a bare delete update, because Telethon documents that delete updates may lack a private-chat peer.

Name, photo and bio mimic options use documented UpdateProfile/profile-photo APIs. Username mimic attempts a small set of available similar candidates when enabled. Personal profile location is exposed as a stored toggle only and is safely skipped where the current Telethon profile API does not expose a writable personal location field.

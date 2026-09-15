# Special V17

- Exact `/بداية الحذف` + `/نهاية الحذف` using the replied-to message as the boundaries.
- Private deletion notifications audited chat-by-chat to avoid false positives from Telegram delete updates without peer context.
- Bot-access log with name, username, ID, status and history.
- Mimic is limited to name, photo, and bio; username/location are never changed. Profile bio is backed up through Telegram full-profile data and is never cleared when the source bio cannot be read.
- `ايقاف البوت` pauses Bot API command handling only; user-account automation, private monitoring, mute/delete and temporary media handling remain active. `تفعيل` resumes the bot.
- All existing V16 files/features retained.

## Runtime notes

Private deletion notifications are produced by per-chat verification rather than trusting a bare delete update, because Telethon documents that delete updates may lack a private-chat peer.

Name, photo and bio mimic options use documented UpdateProfile/profile-photo APIs. Username mimic attempts a small set of available similar candidates when enabled. Personal profile location is exposed as a stored toggle only and is safely skipped where the current Telethon profile API does not expose a writable personal location field.

## V17 Login / Security Update

- V17 remains the base version. This update does not replace V17 with the newer V18 build.
- Access approval happens first. An unapproved user cannot start Telegram-account login.
- After the developer approves the user, `/start` asks that user to log in to their own Telegram account.
- Each approved user gets an independent Telethon session under `storage/sessions/<bot_user_id>/`.
- Telegram login code can be sent with spaces or as separate digit messages; the bot combines the digits automatically.
- Two-step verification is supported when Telegram requests it.
- Phone number, login code, and two-step password are not written to the database or operation logs.
- Existing developer account session remains independent.
- Unauthorized `/start` notifications are sent to the developer only once per user. Attempt 3 restricts the user; attempt 4 bans the user.
- Developer access panel includes blocked users and unban flow by ID or @username.
- Mimic is limited to name, profile photo, and bio. Username is not changed.
- Mimic refuses to start if the original bio cannot be read, preventing accidental loss of the original bio.

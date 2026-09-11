# Special - implementation status

This build keeps the existing Telethon + Aiogram architecture and expands the database/UI foundation.

Implemented in this build:
- private-chat discovery and message statistics
- message archive records
- mute/unmute and muted-message logging
- important-message database and UI foundation
- storage/private menus separated from automation
- broadcast exclusion storage and UI foundation
- protection/settings sections separated
- security/operation logs
- allowed-user database with statuses and access expiry fields
- duration presets: 1, 3, 7, 30, 60, 90 days and lifetime

Not falsely marked as complete:
- Telegram account login for friends: intentionally not implemented; the bot must not collect Telegram login codes or 2FA passwords.
- media-content AI moderation: requires a configured moderation model/service.
- automatic ownership-transfer handling: requires confirming the exact Telegram update/action supported by the current Telethon/Telegram API before enabling an automatic action.
- full broadcast sender and backup file exporter still need their runtime handlers; the UI/data structures are present.

Do not put real .env credentials into the repository.

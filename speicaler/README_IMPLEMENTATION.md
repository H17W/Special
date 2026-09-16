# Special V12 Implementation

Architecture:
- Aiogram for the bot interface and developer/access panel.
- Telethon for the user-account automation.
- SQLite for persistent state.

Secrets:
- Put real values only in local `.env`.
- Keep `.env.example` as a template.
- Keep `.env` and Telethon session files ignored by Git.

Core commands:
- `/بداية` and `/نهاية` work from replied messages in private chats, groups and channels.
- `كتم` and `الغاء الكتم` work by reply in supported chats.
- `تقليد` and `الغاء التقليد` work by reply/mention in supported chats.

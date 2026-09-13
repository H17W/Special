# Special v27

Fresh rebuild of Special based on the full requested feature set.

## Included architecture
- Organized main keyboard and real parent navigation
- Telegram user automation with authorized self-account session
- Private import and unified chronological private log
- Temporary/self-destruct incoming media capture to the bot's Saved Messages, then local deletion after successful send
- Reply-based mimic: `تقليد` / `الغاء التقليد`; name, bio and photo only; rollback + lock
- Reply-based mute and delete range
- AI, Deezer music search, audio to Telegram voice
- Access request flow with one request per pending user
- Temporary access links and restrictions
- Owner-only broadcast with progress/result tracking
- Audit log with pagination-ready DB indexes
- Smart cleanup foundation with category retention and physical storage cleanup
- Health/statistics/backup foundations
- WAL SQLite, indexes, queues, bounded cache, async handlers

## Run
1. Copy `.env.example` to `.env` and fill your own values.
2. `python -m pip install -r app/requirements.txt`
3. `python -m app.main`

Forward Delete is intentionally removed from the architecture and is not part of v27.

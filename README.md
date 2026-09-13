# Special
Telegram Bot + Telegram User Automation.

## Run
```bash
python -m pip install -r app/requirements.txt
cp env.example .env
# fill .env locally
python -m app.main
```

The Telegram user session and runtime data stay outside Git through `.gitignore`.

## Important
- AI uses the official `google-genai` SDK.
- Music search uses Deezer metadata and links; it does not download copyrighted music.
- Temporary-media archiving is limited to incoming private media that Telegram exposes with a TTL/self-destruct period.
- 2FA passwords and Telegram login codes are not stored in SQLite.


## Integration notes
- Telegram must expose a TTL/self-destruct indicator on the incoming private media for temporary-media archiving to trigger; ordinary media is never archived by this feature.
- Telegram voice messages do not support album-cover metadata. The audio workflow preserves title/artist in the outgoing caption; a user-supplied cover can be handled as a separate image if desired.
- Bot API cannot grant Telegram account permissions; group/channel deletion still depends on the logged-in user account's Telegram permissions.

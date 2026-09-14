# Special V6

Fixes the main-menu/back navigation path.

- Main menu callback now explicitly distinguishes owner vs regular users.
- Owner returns to the full main menu without depending on feature_permissions.
- Regular users return with their granular enabled permissions.
- Previous V5 database and callback fixes are retained.


## Private message capture
Every incoming private message is immediately copied to the owner bot chat, including one-character text and messages consisting only of Arabic diacritics. Media is downloaded immediately when possible. Each capture includes sender name, ID, username (or no username) and an "open sender" button.

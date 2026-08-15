# Hot Reload

`main.py`'s `_hot_reload_loop` polls `commands/`, `events/`, `rpg/`, `utils/`, and `database/`
for file changes every 1.5s. On a change, it `importlib.reload()`s plain modules first (so
`rpg/`, `utils/`, `database/` pick up fresh code), then `bot.reload_extension()`s every loaded
cog, then re-syncs the slash command tree. Toggle with `HOT_RELOAD` in `.env`.

See [Infrastructure Overview](Infrastructure%20Overview.md).

# Restart Announcements

`data/restart_state.json` tracks whether the bot is currently `running` or shut down cleanly.
On startup, `GamblerBot.report_startup_state()` compares the previous state and posts to
`RESTART_LOG_CHANNEL_ID`:

- ✅ "Restart complete" if the previous run shut down cleanly
- ⚠️ "Restarted after an unclean shutdown" (with the tail of `logs/debug.log`) if it crashed

`graceful_shutdown()` handles `SIGTERM`/`SIGINT` (not supported on Windows) to mark a clean
shutdown before closing. See [Infrastructure Overview](Infrastructure%20Overview.md) and [Error Handling](Error%20Handling.md).

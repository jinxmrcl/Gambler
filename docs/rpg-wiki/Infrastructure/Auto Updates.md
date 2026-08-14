# Auto Updates

A background task in `main.py` (`_git_watch_loop`), started in `setup_hook` alongside
[Hot Reload](Hot%20Reload.md) — runs in-process, so it shows up in the same logs/process as the bot itself
rather than as a separate service.

Every 60s: pins `origin` to the repo's HTTPS URL (self-healing against a misconfigured remote),
fetches, and if the local commit is behind, runs a fast-forward-only merge (`git merge --ff-only
origin/<branch>` — never a real 3-way merge, so it can't silently create a merge commit or
clobber anything). On a successful pull it posts to `RESTART_LOG_CHANNEL_ID`; on a failed one
(usually uncommitted local changes on the server blocking the fast-forward) it posts a warning
once per failing commit rather than repeating every cycle.

Deliberately does **not** restart the bot itself — code changes to `commands/`, `events/`,
`rpg/`, `utils/`, `database/` get picked up automatically by [Hot Reload](Hot%20Reload.md) regardless, and
anything else (like `main.py` itself) needs an explicit `/restart` (see
[Admin Commands](../Admin%20%26%20Settings/Admin%20Commands.md)).

See [Infrastructure Overview](Infrastructure%20Overview.md).

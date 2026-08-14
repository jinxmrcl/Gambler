# Coinflip 🪙

**PvP** (`/coinflip`): challenge another player for an equal amount each; winner takes the pot
minus the house edge. Accept/Decline via buttons. Not individually toggleable (no `game_enabled`
check) since it's a player-vs-player wager, not a house game.

**Solo** (`/soloflip`, alias `/cf`): call heads or tails against the house. Win chance is
randomized per flip (46.5%-50.5%, never a fixed 50%) so it can't be pinned down by watching
outcomes, but averages out to the same house edge — a clean 2x payout on a win.

See [[Casino Overview]] and [[../Social/Social Overview]] for other PvP features.

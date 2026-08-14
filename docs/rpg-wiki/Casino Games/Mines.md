# Mines 💣

Customizable grid: `cols` (2-5) x `rows` (2-5), player picks how many mines are hidden. Reveal
tiles to build a growing multiplier; cash out anytime before hitting a mine. Default is the
original 5x4 (20 tiles, up to 19 mines); the full 5x5 grid unlocks up to 23 mines for much
higher risk/reward — the layout shares the last row between tiles and the Cash Out button
(instead of giving Cash Out its own row) to fit that many tiles within Discord's 5-action-row
limit per message.

Multiplier is the fair hypergeometric odds of avoiding all mines so far, scaled down by the
house edge. See [[Casino Overview]].

# Bank

- `/bank` — shows cash and the bank balance for the current server
- `/deposit` / `/withdraw` — move money between wallet and bank (accepts a number, `half`, or `all`)

Money in the bank can't be stolen by [`/rob`](Hustle%20%28Work%20Crime%20Rob%29.md). Banked money is
stored separately for each server, so it can't be withdrawn from another server. Deposits/withdrawals run
as atomic transactions. See [Economy Overview](Economy%20Overview.md).

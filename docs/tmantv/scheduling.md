# Scheduling and ads

## Keeping the schedule filled

`fs42_local/keep_schedule.py` checks every channel and only rebuilds one that has less than 1 day of schedule left (or has run out). It then fills it to `SCHEDULE_DAYS` ahead (7 by default, set in `boot.conf`). It runs at boot and nightly at 4:10, so channels don't run out of schedule.

Run it by hand:

```bash
cd ~/FieldStation42 && env/bin/python3 fs42_local/keep_schedule.py 7
```

Log: `fs42_local/logs/schedule.log`.

Rebuilding one named station with `station_42.py -r` no longer trims the whole file cache.

## Better ad rotation

FieldStation42 picks the least-played commercial or bump each time. Upstream only saved play counts for shows, so every schedule run started all ads back at zero and the same ones repeated day after day. T-ManTV saves commercial and bump play counts with each run, so the least-played ads really do go first across days. This is in `fs42/liquid_schedule.py`, with a test in `test/test_break_play_counts.py`.

## Staying on the clock

Streams take a moment to load, and small delays add up over a day. Two rules keep channels on time:

- **Late blocks.** If a block starts late, its show starts from the top and ads are dropped until the channel is back on time. You don't tune in to an episode a few minutes in.
- **Commercial-free channels.** An episode that's up to 120 s late still starts from the top. The lateness carries over and is caught up later (by an [Up Next card](on-screen-extras.md#up-next-card) if the channel has one). A channel change always rejoins the real clock.

Both are in `play_slot` in `fs42/station_player.py`.

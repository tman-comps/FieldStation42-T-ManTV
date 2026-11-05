# Commands and troubleshooting

## Helper commands

Installed to `~/.local/bin` from `pi/home/.local/bin`.

| Command | What it does |
|---|---|
| `fs42-start` | Start everything and go back to the last channel |
| `fs42-stop` | Stop everything and remember the channel |
| `fs42-restart` | Restart only the player (about 3 s), same channel |
| `fs42-restart-all` | Full stop and start. Use after editing `boot.conf`. |
| `fs42-log` | Recent launcher and schedule lines, then the live player log |
| `fs42-osd` / `fs42-osd-stop` | Start / stop the OSD (rating bug) |
| `fs42-mkv-proxy serve [port]` | Run the archive.org index proxy (cron does this) |
| `fs42-mkv-proxy fill <dir>` | Pre-cache the index of every stub under a folder |
| `fs42-mkv-proxy-restart` | Restart the proxy |
| `fs42-desktop` | Show the taskbar and desktop until the next reboot (handy over VNC) |
| `tv-margins [L R T B]` | Set or re-apply the composite edge margins |
| `fs42-tune-back [save]` | Save the current channel, or tune back to the saved one |

## Logs

All in `~/FieldStation42/fs42_local/logs/` unless noted.

| Log | What |
|---|---|
| `launcher.log` | Boot, NAS wait, player restarts |
| `field_player.log` | The player |
| `remote.log` | Every button press and where it went |
| `guide_overlay.log` | Guide, On Demand, banners, reminders |
| `schedule.log` | Schedule top-ups |
| `archive_urls.log` | Direct link refreshes |
| `ondemand_export.log` | Nightly On Demand export |
| `~/.cache/fs42-mkv-proxy.log` | Index proxy |
| `~/.cache/fs42-osd.log` | OSD |

Logs over 20 MB are rotated at start.

## Runtime files

In `~/FieldStation42/runtime/` (not in git):

| File | What |
|---|---|
| `reminders.json` | Guide reminders |
| `ondemand_positions.json` | On Demand watch positions |
| `archive_urls.json` | Direct archive.org links |
| `archive_stubs.json` | Cached stub text |
| `beds/` | Music beds and `beds.json` |

## Common problems

**Guide, remote or On Demand calls fail with 401/403.** Upstream API key auth is on. T-ManTV's pages and `remote.py` don't send a key, so leave auth off (don't run upstream's newer `install.sh`).

**Remote does nothing.** Check `remote.log`. If it says no device was found, set `REMOTE_NAME` in `remote.py` to part of your remote's name from `cat /proc/bus/input/devices`.

**Guide button tunes to channel 2 instead of opening over the show.** `guide_overlay.py` isn't running. Check `guide_overlay.log` (it needs PySide6 with QtWebEngine).

**A streamed channel shows TECHNICAL DIFFICULTIES.** archive.org is slow or down, or the link went stale. Run `env/bin/python3 fs42_local/archive_urls.py 0` to re-check every link.

**Choppy picture on some files.** High-bitrate 720p and up can be too much for a Pi 4. Use a lighter copy.

**On Demand is missing new shows.** Rebuild the catalog, then run the export (see [On Demand](ondemand.md#running-the-export-by-hand)).

**No rating bug.** Make sure the file or its `tvshow.nfo` has a rating, a matching image is in `osd/ratings/`, the catalog was rebuilt, and `fs42-osd` is running.

**Picture cut off at the edges.** Adjust `tv-margins`, or the shrink in `mpv.conf`.

# Setup

T-ManTV runs on a Raspberry Pi 4 with Raspberry Pi OS (desktop, X11), driving a CRT over composite. Media can live on a NAS or a local disk. It has only been tested on that setup.

## 1. Install FieldStation42's requirements

Follow upstream's install steps ([README.upstream.md](../../README.upstream.md), or https://fieldstation42.com/docs/) for the system packages and Python venv, but clone **this** repo:

```bash
git clone -b tmantv https://github.com/tman-comps/FieldStation42-T-ManTV ~/FieldStation42
cd ~/FieldStation42
python3 -m venv env && env/bin/pip install -r install/requirements.txt
```

Don't run upstream's `install.sh` on top. Newer versions turn on API key auth, and the guide, remote and On Demand calls don't send a key.

The remote listener also needs `evdev` in the venv (`env/bin/pip install evdev`). PySide6, used by the guide overlay, is already in the requirements. The OSD helper uses `xcompmgr` (`sudo apt install xcompmgr`).

## 2. Boot settings

```bash
cp fs42_local/boot.conf.example fs42_local/boot.conf
nano fs42_local/boot.conf
```

| Setting | What it does |
|---|---|
| `NAS_MOUNT` | Where the media is mounted. Boot waits for it. |
| `NAS_WAIT` | Seconds to wait for the NAS before starting anyway (default 180) |
| `SPLASH` | Image shown while waiting. `fs42_local/make_standby.py` makes one. |
| `XRANDR_OUTPUT` / `XRANDR_TRANSFORM` | Video output name and an optional xrandr transform |
| `HIDE_DESKTOP` | `1` hides the taskbar and desktop icons (`fs42-desktop` brings them back) |
| `SCHEDULE_DAYS` | When a channel has under 1 day left, refill it to this many days |
| `TV_IR_HOOK` | Optional webhook for TV power/volume over IR (see [Remote](remote.md#tv-power-and-volume)) |

Run `fs42-restart-all` after changing it.

## 3. Helpers and desktop files

```bash
mkdir -p ~/.local/bin
cp pi/home/.local/bin/* ~/.local/bin/
cp pi/home/ondemand_export.py ~/
cp -r pi/home/.config/* ~/.config/
```

That copies:
- the `fs42-*` commands (see [Commands](commands.md))
- `autostart/fs42.desktop`, which runs `start_fs42.sh` when the desktop logs in
- `autostart/tv-margins.desktop`, which applies the composite edge margins
- the LXDE autostart with the taskbar off
- `mpv/mpv.conf` with the OSD style and the CRT shrink filter

## 4. Cron jobs

Add the lines from [`pi/crontab.example`](../../pi/crontab.example) with `crontab -e`. They:

| Time | Job |
|---|---|
| 4:10 | Top up any channel's schedule that's running low |
| 4:40 | Refresh the direct archive.org links |
| boot + every minute | Keep the archive.org proxy running |
| 4:50 | Rebuild the On Demand menu from the catalog |

## 5. Channels

Add your station configs in `confs/` (see upstream's [station config docs](../STATION_CONFIG_README.md) and `confs/examples/`), then build:

```bash
env/bin/python3 station_42.py -x --skip_chapter_scan
```

Make channel 2 the i-Guide channel if you want the full-screen guide as a channel too. The Guide button works without it.

## 6. Optional extras

- **Rating bug:** add the `RatingDisplay` block to `osd/osd.json` and run `fs42-osd`. See [On-screen extras](on-screen-extras.md#rating-bug).
- **Up Next card:** add `up_next` to a channel. See [On-screen extras](on-screen-extras.md#up-next-card).
- **Newspaper guide:** copy `extras/newspaper-guide` to `~/fs42-tv-guide`, run `npm install`, make `.env` from `.env.example`, and install `pi/etc/systemd/system/fs42-tv-guide.service` (change `User` and paths to yours). It serves on port 3000.

## 7. Start it

```bash
fs42-start
```

Or reboot. Watch it come up with `fs42-log`.

## What happens at boot

`start_fs42.sh` runs these in order:

1. Turns off screen blanking and applies the xrandr settings.
2. Shows the standby splash.
3. Waits for the NAS (tries to mount it every 15 s, up to `NAS_WAIT`).
4. Refreshes archive.org links in the background.
5. Tops up schedules (`keep_schedule.py`).
6. Starts `remote.py` and `guide_overlay.py`, each in a loop that restarts it if it exits.
7. Starts `field_player.py`, hides the splash after 8 s, and restarts the player if it ever exits.

Everything stops when `fs42-stop` creates `fs42_local/STOP`.

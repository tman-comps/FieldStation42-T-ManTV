# T-ManTV — a FieldStation42 fork

This is a fork of [FieldStation42](https://github.com/shane-mason/FieldStation42) by Shane Mason, the cable/broadcast TV simulator for a Raspberry Pi. It's the code behind T-ManTV, a home retro-TV box: a Raspberry Pi 4 driving a CRT over composite, with the media on a NAS.

Upstream's README (setup, configuration, scheduling) is still the main manual: [README.upstream.md](README.upstream.md) and the official docs at https://fieldstation42.com/docs/. This page only covers what's different here.

**Bring your own content.** The repo has code only: no media, catalogs, channel configs or show lists.

## What's added

- **Internet Archive streaming (`.strm` stubs).** A channel can play archive.org videos without downloading them. Each episode is a small text file with the stream URL, so the catalog, schedule, NFO guide text and play counts all work as with local files.
- **Fast archive.org tuning.** `fs42_local/archive_urls.py` caches the direct download links (no ~2 s redirect at every tune). `fs42-mkv-proxy` is a small local proxy that serves those files with a seek index, so channel changes take about 1 s.
- **Live volume leveling for streams.** Streams go through mpv `loudnorm` (-18 LUFS) so archive.org uploads match local files. Local files play without it.
- **CRT-friendly picture.** mpv shrinks the picture a little during effects (overscan), keeps a stub's side-bar crop through channel-change static, and shows a big green channel number on tune.
- **Boot and autostart** (`fs42_local/start_fs42.sh`): waits for the NAS while showing a standby splash, starts the player, and keeps the schedule filled (`keep_schedule.py`). Helpers in `pi/home/.local/bin`: `fs42-start`, `fs42-stop`, `fs42-restart`, `fs42-log`, and more.
- **Remote control** (`fs42_local/remote.py`): an IR/USB remote via evdev plus a phone remote page on port 4244. Number keys tune channels, and there are buttons for the guide, On Demand and last channel. TV power/volume can optionally go to a Home Assistant IR webhook (`TV_IR_HOOK` in `boot.conf`).
- **i-Guide**: an interactive on-screen guide channel you can scroll with the remote (based on the FieldStation42Expanded i-Guide), with themes and a live picture overlay.
- **On Demand**: a menu of shows and movies from your catalog. You open it from the remote or by dialing 99, and it picks up where you left off. `pi/home/ondemand_export.py` builds the menu nightly from `confs/`.
- **Newspaper TV guide** (`extras/newspaper-guide/`): a printable, newspaper-style web guide on port 3000.
- Smaller fixes: a named `station_42.py -r` doesn't trim the file cache, seek at load (no gap before the picture), NFO plot for music videos, short guide blocks, and ended shows hidden in the guide.

## Hardware

- Raspberry Pi 4 (Raspberry Pi OS with desktop, X11) with composite out to a CRT.
- Media on a NAS mounted at `/mnt/nas` (set it in `boot.conf`), or local disk.
- Optional: a USB/IR remote, a Broadlink + Home Assistant for TV power.

## Fresh Pi install

1. Install FieldStation42's requirements as upstream describes, but clone **this** repo to `~/FieldStation42` and check out `tmantv`. Don't run upstream's `install.sh` on top (newer versions turn on API key auth, which the guide, remote and On Demand calls don't send).
2. `cp fs42_local/boot.conf.example fs42_local/boot.conf` and edit it (NAS mount, splash, optional `TV_IR_HOOK`).
3. Copy the helpers: `cp pi/home/.local/bin/* ~/.local/bin/`, `cp pi/home/ondemand_export.py ~/`, and the files under `pi/home/.config/` to `~/.config/` (autostart entry, LXDE autostart with the panel off, `mpv.conf` with the OSD style).
4. Cron: add the lines from `pi/crontab.example` with `crontab -e` (schedule top-up, archive link refresh, the proxy, On Demand export).
5. Newspaper guide (optional): copy `extras/newspaper-guide` to `~/fs42-tv-guide`, run `npm install`, create `.env` from `.env.example`, then install `pi/etc/systemd/system/fs42-tv-guide.service` (change `User`/paths to yours).
6. Add your stations in `confs/`, build with `python3 station_42.py -x --skip_chapter_scan`, then `fs42-start` (or reboot).

## Internet Archive `.strm` stubs

Put stubs in a folder whose name contains `(Archive)` and link that folder under `catalog/<station>/<tag>/`. Line 1 is the URL. Other lines are options:

```
http://127.0.0.1:8742/<item>/<file>.mp4
#duration=1720.74
#start=23
#crop=640:480:0:0
#aid=1
```

| Line | Meaning |
|---|---|
| line 1 | Stream URL: `https://archive.org/download/<item>/<file>`, or the local proxy `http://127.0.0.1:8742/<item>/<file>` (faster tunes) |
| `#duration=` | Length in seconds (required; the catalog build doesn't go online) |
| `#start=` | Skip the first N seconds (trim leaders). Duration is the trimmed length. |
| `#crop=` | mpv crop `w:h:x:y` to remove side or top bars (find it with ffmpeg `cropdetect`) |
| `#aid=` | Audio track to play (for uploads with a commentary or second-language track) |

A matching `.nfo` next to the stub gives the guide its title and plot. After adding or editing stubs, run `env/bin/python3 fs42_local/archive_urls.py` and `~/.local/bin/fs42-mkv-proxy fill catalog/<station>`.

## Known limits

- Built and tested only on one Pi 4 + composite CRT setup. Other outputs and HDMI aren't tested.
- Streams need a steady connection; archive.org outages show as static or skip to the next file.
- Heavy files (high-bitrate 720p+) may not decode smoothly on a Pi 4. Drop them or use a lighter copy.
- `fs42_local/apply_patches.py` is from before the fork, when the changes were re-applied at every start. It's being retired; the changes are now normal commits.
- Corner logos are turned off on this setup.

## Credits and licenses

- **FieldStation42** © Shane Mason and contributors, [MPL-2.0](LICENSE). This fork stays MPL-2.0; changed files keep their MPL headers.
- **i-Guide** comes from FieldStation42Expanded, MPL-2.0.
- **Newspaper TV guide** ([sandyjmacdonald/fs42-tv-guide](https://codeberg.org/sandyjmacdonald/fs42-tv-guide)) © Sandy Macdonald, MIT; see `extras/newspaper-guide/LICENSE`.
- Fonts: Press Start 2P and Bungee Shade (SIL OFL); Star4000 fonts as shipped with the i-Guide.
- T-ManTV changes are under MPL-2.0 (the newspaper guide changes are under MIT).

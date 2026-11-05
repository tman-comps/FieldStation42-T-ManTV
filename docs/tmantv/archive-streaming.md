# Internet Archive streaming

A channel can play videos straight from archive.org without downloading them. Each episode is a small `.strm` text file (a stub) holding the stream URL. FieldStation42 treats stubs like normal video files, so the catalog, schedule, NFO guide text and play counts all work the same.

## Making stubs

Put stubs in a folder whose name contains `(Archive)`, and link that folder under `catalog/<station>/<tag>/` like any other content.

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
| `#duration=` | Length in seconds. **Required**, because the catalog build doesn't go online. |
| `#start=` | Skip the first N seconds (cuts leaders). `#duration` is the length after trimming. |
| `#crop=` | mpv crop `w:h:x:y` to remove black bars. Find it with ffmpeg `cropdetect`. |
| `#aid=` | Which audio track to play (for uploads with commentary or a second language) |
| `#music=` | Play a music bed under the video (see below) |
| `#ambient=` | With `#music`, how loud the video's own sound stays, 0 to 1 (default 0.15) |

Line 1 can also be a path on the NAS.

A matching `.nfo` next to the stub gives the guide its title and plot. For the rating bug, one `tvshow.nfo` in the show folder covers every episode.

After adding or editing stubs:

```bash
cd ~/FieldStation42
env/bin/python3 fs42_local/archive_urls.py
~/.local/bin/fs42-mkv-proxy fill catalog/<station>
```

Then rebuild the catalog for that station.

## Why tuning is fast

A plain archive.org link is slow to open: about 2 s for the redirect, plus several more requests to read the file's index. T-ManTV cuts that to about 1 s per channel change:

1. **Direct links.** `fs42_local/archive_urls.py` looks up each file's direct server link (`dnNNN.*.archive.org`) and saves it in `runtime/archive_urls.json`. It runs at boot and nightly, and re-checks links older than 48 hours. If a direct link fails, the player retries through the normal redirect.
2. **Stub cache.** The same script saves each stub's text to `runtime/archive_stubs.json`, so tuning doesn't wait on the NAS.
3. **Index proxy.** `fs42-mkv-proxy` (port 8742) keeps a local copy of each file's index: the start and end of an MKV, or the `moov` block of an MP4. Opening a file mid-episode then needs about one request to archive.org instead of six. `fill` pre-caches every stub under a folder. Cron keeps the proxy running. If the proxy is down, the player goes straight to archive.org.

## Volume leveling

Streams go through mpv's `loudnorm` filter at −18 LUFS, so archive.org uploads play at about the same volume as local files. Local files play without it.

## If archive.org is down

The channel shows TECHNICAL DIFFICULTIES or moves on to the next file. The remote keeps working while a stream loads.

## Music beds

A stub can play a long music track under its video, like a weather channel's background music. The music runs like a radio station: it's at a clock-based spot when you tune in, not restarting from the top each time.

1. Put the music files in `runtime/beds/`, leveled ahead of time.
2. List them in `runtime/beds/beds.json`:

   ```json
   { "smooth-jazz": { "file": "smooth-jazz.opus", "length": 14400 } }
   ```

   `length` is the file's length in seconds.
3. Add to the stub:

   ```
   #music=smooth-jazz
   #ambient=0.15
   ```

`#ambient=0` plays only the music (also works for videos with no sound). The mix assumes the video has one audio track.

How it works: the player writes an mpv EDL (`runtime/beds/now_playing.edl`) that starts the bed at the right spot and loops it for as long as the video runs, loads it as an extra audio track, and mixes the two with `lavfi-complex`.

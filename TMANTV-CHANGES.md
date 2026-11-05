# T-ManTV changes to FieldStation42 code

Where each change lives. For how to use each feature, see the [feature guides](docs/tmantv/README.md). Most of these used to be find/replace entries in `fs42_local/apply_patches.py`; the code is now committed. In-code comments are tagged `FS42 local:`.

| Change | Where |
|---|---|
| CRT shrink kept during effects (mpv.conf `vf=` appended to every filter) | `fs42/tmantv.py` `ShrinkMPV`, used as `MPV` in `fs42/station_player.py` |
| Seek inside the first load (no pre-seek frame flash), keyframe seeks (`hr_seek=no`, 20 s tolerance) | `station_player.py` `play_file`, `_seek_with_verify` |
| Channel number (mpv `show-text`) on button press, at startup and after the new video starts | `field_player.py` (`_fs42_osd_pending`), `station_player.py` `play_file` |
| Web channel muted when you leave it; leftover QtWebEngine audio killed | `fs42/webrender/web_render.py`, `station_player.py` web channel start/stop |
| `.strm` stubs in catalog scans; duration from `#duration=` | `fs42/media_processor.py` |
| `.strm` playback: URL or NAS path, `#start`, `#crop`, `#aid` | `tmantv.read_stub`, `station_player.py` `play_file` |
| Archive down → TECHNICAL DIFFICULTIES; remote works while a stream loads | `station_player.py` `play_slot`, `play_file` |
| Direct archive.org links (`runtime/archive_urls.json`), retry through the redirect | `tmantv.direct_url`, `play_file` wait loop; filled by `fs42_local/archive_urls.py` |
| Stub text cache (`runtime/archive_stubs.json`): tunes skip the NAS | `tmantv.stub_text` / `open_stub` |
| Local index proxy (`fs42-mkv-proxy`), falls back to archive.org | `tmantv.proxy_up` / `proxy_to_archive`, `play_file` |
| Live loudness leveling for streams (`@fs42level` loudnorm) | `play_file` |
| Resumed stream pieces end by their real position (mid-show breaks) | `play_file` (`_fs42_seek_target`), `play_slot` |
| Ad catch-up: a late block starts its show from the top and drops ads until on time | `play_slot` |
| On Demand playback | `station_player.py` `play_ondemand`, `field_player.py` main loop |
| i-Guide arrow/Home keys allowed | `fs42/fs42_server/api/ppv.py`, `web_render.py` |
| Named `station_42.py -r` skips the file cache trim | `station_42.py` |
| NFO "now playing" overlay off (froze playback); music video NFOs read `plot` | `fs42/nfo_agent.py` |
| Guide: short blocks, ended shows hidden, `.program-desc`, 90s CRT theme | `fs42/fs42_server/static/customguide/` |
| Logo fade in/out | `fs42/osd/logo_display.py` (old OSD only; logos are off) |
| Rating bug (TV-Y7, PG-13… top-right for 12 s when a show starts; never on ads). From MoeFwacky's fork, plus: keeps image shape, reads a show folder's `tvshow.nfo` when a file has no rating | `fs42/osd/rating_display.py`, `nfo_agent.py` `folder_rating`, `media_processor.py` `extract_metadata`, `tmantv.content_rating`, `station_player.py` status socket; images in `osd/ratings/` |
| Up Next card before each episode (channels with `up_next`); stream-load lateness eats into the card so episodes start from the top | `fs42/autobump_agent.py` `up_next_bump`, `fs42/liquid_schedule.py`, `station_player.py`; page `fs42/fs42_server/static/upnext/upnext.html` |
| Commercial-free channels: a straight-on episode up to 120 s late starts from the top | `station_player.py` `play_slot` |
| Commercial and bump play counts saved with each schedule run (least-played ads first across days) | `fs42/liquid_schedule.py`; test `test/test_break_play_counts.py` |
| Guide themes: ws / cable / modern / vcr for guide, banner, reminder pop-up and Up Next card, and station name, set with `fs42_local/guide-theme` (`iguide/settings.json`) | `static/iguide/tmantv_theme.js`, `themes/<name>.css`, `themes/<name>-upnext.css`, `fs42_local/guide-theme` |
| Channel-change info banner (WeatherStar bar, 4 s) | `fs42_local/guide_overlay.py`, `static/iguide/tmantv_skin.js` `tmanBanner` |
| i-Guide Left/Right = 30 min per press, schedule windows cached and prefetched | `static/iguide/tmantv_skin.js` |
| Reminders: OK on a future show sets/clears one (`runtime/reminders.json`); pop-up at start time, OK = watch, Back = dismiss | `fs42_local/guide_overlay.py`, `fs42_local/remote.py` `reminder_key`, `tmantv_skin.js` `tmanReminder`, `themes/ws.css` |
| Music beds for stubs (`#music=`, `#ambient=`): a clock-synced bed from `runtime/beds` mixed in the same mpv | `tmantv.music_setup` / `set_music` / `music_track`, `station_player.py` `play_file` |

## Up Next setup

Add `up_next` inside a station's `station_conf`. All keys are optional:

```json
"up_next": { "duration": 20, "accent": "#ff9a1a", "ticker": "Stay tuned!", "music": "0" }
```

`duration` is the card length in seconds. `header` replaces the network name under "Up Next"; `accent` is the header color. Music is off unless you put WeatherStar-style tracks in `static/upnext/music/` as `ws01.mp3` … `ws12.mp3` (not in the repo); `"music": "0"` skips it.

## Rating bug setup

The rating comes from `<mpaa>` or `<certification>` in a file's own `.nfo`, or else from the nearest `tvshow.nfo` (file's folder, up to 3 levels up; works for `.strm` stubs). Movies only use their own NFO. It is saved at catalog build, so rebuild the catalog after adding ratings. The image is `osd/ratings/<RATING>.png` (name match ignores case; `US:` and `Rated ` are dropped). No rating or no image = no bug.

Turn it on: add this to `osd/osd.json` (not tracked) and run the OSD (`fs42/osd/main.py`, started by `~/.local/bin/fs42-osd`). The margins match the old logo spot inside the CRT's overscan; the channel number stays top-left.

```json
{ "type": "RatingDisplay", "directory": "osd/ratings", "halign": "RIGHT", "valign": "TOP",
  "width": 0.08, "height": 0.12, "x_margin": 0.22, "y_margin": 0.13, "display_time": 12.0 }
```

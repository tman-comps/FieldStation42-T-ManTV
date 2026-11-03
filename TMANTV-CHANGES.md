# T-ManTV changes to FieldStation42 code

Where each change lives. Most of these used to be find/replace entries in `fs42_local/apply_patches.py`; the code is now committed. In-code comments are tagged `FS42 local:`.

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

#!/bin/bash
FS42="$HOME/FieldStation42"; LOCAL="$FS42/fs42_local"; LOG="$LOCAL/logs"
mkdir -p "$LOG"
exec 9>/tmp/fs42-launcher.lock
flock -n 9 || exit 0                      # already running
source "$LOCAL/boot.conf"
export TV_IR_HOOK
export DISPLAY=:0
cd "$FS42" || exit 1
log() { echo "$(date '+%F %T') $*" >> "$LOG/launcher.log"; }
for f in "$LOG"/*.log; do [ -f "$f" ] && [ "$(stat -c%s "$f")" -gt 20000000 ] && mv "$f" "$f.old"; done
log "launcher start"

for i in $(seq 1 60); do xset q >/dev/null 2>&1 && break; sleep 1; done   # wait for the desktop session
xset s off -dpms s noblank 2>/dev/null                                      # never blank the TV
xrandr --output "$XRANDR_OUTPUT" --transform none      # reset first
if [ -n "$XRANDR_TRANSFORM" ]; then
  # keep the screen at the TV's real size (xrandr otherwise enlarges it, pushing apps off-screen)
  MODE=$(xrandr | awk -v o="$XRANDR_OUTPUT" '$1==o{f=1;next} f&&/\*/{print $1; exit}' | sed 's/[^0-9x].*//')
  xrandr --output "$XRANDR_OUTPUT" --transform "$XRANDR_TRANSFORM" ${MODE:+--fb $MODE}
  log "xrandr transform applied, screen kept at ${MODE:-unknown}"
fi

mpv --fs --no-osc --no-input-default-bindings --image-display-duration=inf "$SPLASH" >/dev/null 2>&1 9>&- &
SPLASH_PID=$!

for i in $(seq 1 "$NAS_WAIT"); do
  if mountpoint -q "$NAS_MOUNT" && [ -n "$(ls -A "$NAS_MOUNT" 2>/dev/null | head -1)" ]; then
    log "NAS ready after ${i}s"; break
  fi
  [ $((i % 15)) -eq 1 ] && sudo -n mount "$NAS_MOUNT" >/dev/null 2>&1
  [ "$i" -eq "$NAS_WAIT" ] && log "WARNING: NAS not ready after ${NAS_WAIT}s, starting anyway"
  sleep 1
done

source env/bin/activate
# apply_patches.py is no longer run: its changes are normal commits in this fork now
# (running it on the committed code would insert some blocks a second time).
# direct archive.org links + stub text cache (refreshes links older than 2 days)
( flock -n "$LOCAL/.archive_urls.lock" python3 "$LOCAL/archive_urls.py" >> "$LOG/archive_urls.log" 2>&1 ) 9>&- &
flock "$LOCAL/.schedule.lock" python3 "$LOCAL/keep_schedule.py" "$SCHEDULE_DAYS" >> "$LOG/schedule.log" 2>&1

# remote control listener (restarts itself if it ever exits)
( while [ ! -f "$LOCAL/STOP" ]; do python3 "$LOCAL/remote.py" >> "$LOG/remote.log" 2>&1; sleep 3; done ) 9>&- &

# guide overlay: i-Guide over the live show, opened by the Guide button (restarts itself if it exits)
( while [ ! -f "$LOCAL/STOP" ]; do python3 "$LOCAL/guide_overlay.py" 2>&1 | grep --line-buffered -v "gbm_wrapper" >> "$LOG/guide_overlay.log"; sleep 3; done ) 9>&- &

while [ ! -f "$LOCAL/STOP" ]; do
  log "starting field_player"
  python3 field_player.py -t long >> "$LOG/field_player.log" 2>&1 9>&- &
  PID=$!
  if [ -n "$SPLASH_PID" ]; then sleep 8; kill "$SPLASH_PID" 2>/dev/null; SPLASH_PID=""; fi
  wait "$PID"
  log "field_player exited (code $?)"
  pkill -9 -x mpv
  sleep 3
done
log "stopped (fs42-stop)"

# Remote control

`fs42_local/remote.py` turns remote buttons into TV actions. It works with a USB/IR remote (built for an MX3 air-mouse dongle) and with a phone remote page. Both go through the same routing, so they behave the same.

## The USB/IR remote

`remote.py` opens every input device whose name contains `REMOTE_NAME` (`"USB Composite Device"` for the MX3 dongle; it shows up as a keyboard, a consumer-control device and a mouse). It grabs them, so presses don't leak into the desktop or web pages.

To use another remote, change `REMOTE_NAME` at the top of `remote.py` to part of its device name (`cat /proc/bus/input/devices` lists them). Key names are standard evdev names, so most remotes need no other change.

## Phone remote

Open `http://<pi>:4244/` on a phone on the same network. It has Guide, On Demand, Back, a D-pad with OK, volume, mute, channel up/down and a number pad.

## What the buttons do

What a button does depends on what's on screen. `remote.py` checks in this order: reminder pop-up, guide overlay, On Demand, i-Guide channel, then normal TV.

### Watching TV

| Button | Action |
|---|---|
| Numbers | Tune. It waits 1.2 s for a second or third digit. |
| Up / Down, CH +/− | Channel up / down |
| Left / Right, VOL +/− | TV volume down / up (needs `TV_IR_HOOK`) |
| Mute | TV mute (needs `TV_IR_HOOK`) |
| Guide (Home/Menu) | Open the guide over the show. Press again to close. |
| On Demand (clapper button) | Open the On Demand menu |
| `9` `9` | Also opens On Demand |
| Back | Last channel |
| Power | TV power, if `TV_IR_HOOK` is set |

### Guide open

| Button | Action |
|---|---|
| Up / Down, CH +/− | Move between channels |
| Right / Left | Move 30 minutes later / earlier |
| OK on a show that's on now | Tune to it (Back then returns to what you were watching) |
| OK on a future show | Set or clear a reminder |
| Back | Close the guide |
| Numbers | Close the guide and tune |

The guide closes itself after 2 minutes with no presses.

### Reminder pop-up

| Button | Action |
|---|---|
| OK | Tune to that show |
| Back | Dismiss |

Other buttons work as normal.

### On Demand menu

| Button | Action |
|---|---|
| Arrows | Move around the menu |
| OK | Open / play |
| Back | Step back (closes the menu at the top) |
| Numbers | Close the menu and tune |

### On Demand title playing

| Button | Action |
|---|---|
| OK | Pause / play |
| Left | Back 10 s |
| Right | Ahead 30 s |
| Back | Return to the menu |
| CH, numbers, Guide, volume | Work as normal |

## TV power and volume

The Pi can't power a CRT on or off by itself. If you set `TV_IR_HOOK` in `boot.conf` to a webhook URL, Power, volume and mute send a POST with `{"key": "power"}` (or `vol_up`, `vol_down`, `mute`) to it. On T-ManTV this is a Home Assistant webhook that runs a script driving a Broadlink IR blaster.

Volume is the TV's own volume, not the Pi's. With `TV_IR_HOOK` empty, the power, volume and mute buttons do nothing, so use the TV's own remote for those.

## Settings at the top of `remote.py`

| Setting | Default | Meaning |
|---|---|---|
| `REMOTE_NAME` | `USB Composite Device` | Part of the remote's input device name |
| `DIGIT_WAIT` | 1.2 | Seconds to wait for more digits |
| `DEBOUNCE` | 0.25 | Ignore repeats faster than this |
| `GUIDE_CHANNEL` | 2 | The full-screen i-Guide channel |
| `ONDEMAND_CHANNEL` | 99 | Dialing this opens On Demand |
| `WEB_PORT` | 4244 | Phone remote port |

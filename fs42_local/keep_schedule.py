# Tops up a channel's schedule ONLY when it has less than 1 day left
# (or has run out), then fills it to N days ahead (default 7).
import datetime, os, sys
os.chdir(os.path.expanduser("~/FieldStation42"))
sys.path.insert(0, os.getcwd())
from fs42.station_manager import StationManager
from fs42.liquid_manager import LiquidManager
from fs42.liquid_schedule import LiquidSchedule

days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
now = datetime.datetime.now()
low_mark = now + datetime.timedelta(days=1)
target = now + datetime.timedelta(days=days)
stamp = now.strftime("%Y-%m-%d %H:%M")
for st in StationManager().stations:
    if not st.get("_has_schedule"):
        continue
    name = st["network_name"]
    try:
        end = LiquidSchedule(st)._end_time()
        if end is not None and end >= low_mark:
            print(f"{stamp} {name}: fine, scheduled through {end} - nothing to do", flush=True)
            continue
        if end is None or end < now:
            print(f"{stamp} {name}: schedule missing or ran out ({end}) - rebuilding", flush=True)
            LiquidManager().reset_schedule(st)
        else:
            print(f"{stamp} {name}: under 1 day left (ends {end}) - topping up", flush=True)
        added = 0
        while added < days * 3:
            end = LiquidSchedule(st)._end_time()
            if end is not None and end >= target:
                break
            LiquidSchedule(st).add_days(1)
            added += 1
        print(f"{stamp} {name}: scheduled through {LiquidSchedule(st)._end_time()} (+{added} days)", flush=True)
    except Exception as e:
        print(f"{stamp} {name}: ERROR {e}", flush=True)

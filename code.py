# code.py -- runner loop. CircuitPython always runs this file on boot.
# It launches the currently selected program and swaps between programs on
# UP/DOWN button presses without soft-rebooting the board.
#
# Programs are registered in app_switch.PROGRAMS.

import gc
import sys
import supervisor
import time
import app_switch
import display_common

idx = app_switch.current_index()
loads = 0
while True:
    name = app_switch.PROGRAMS[idx]
    mod = name[:-3]
    try:
        __import__(mod)                    # runs the app's top-level loop until SwitchRequested
    except app_switch.SwitchRequested as e:
        idx = app_switch.next_index(idx, e.direction)
        app_switch._write_index(idx)
    except Exception as e:                  # app crashed (wifi down at boot, bad JSON...)
        print("App crashed:", name, repr(e))
        display_common.show_error("ERR " + mod[:6])   # 3-line message
        time.sleep(5)                       # then move on to the SAME app again via reload
        supervisor.reload()
    sys.modules.pop(mod, None)
    gc.collect()
    loads += 1
    if loads % 8 == 0 or gc.mem_free() < 150000:
        supervisor.reload()                 # fragmentation safety net; index is persisted

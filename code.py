# code.py -- launcher. CircuitPython always runs this file on boot; its only
# job is to hand off to whichever program was last selected (persisted by
# app_switch.py) and boot straight into it.
#
# To add/rename programs, edit PROGRAMS in app_switch.py.

import supervisor
import app_switch

idx = app_switch.current_index()
target = app_switch.PROGRAMS[idx]
print("Booting into", target)
supervisor.set_next_code_file(target)
supervisor.reload()

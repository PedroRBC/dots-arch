-- Hyprland default apps
TERMINAL     = "kitty"
FILE_MANAGER = "dolphin"
BROWSER      = "helium-browser"
EDITOR       = "gnome-text-editor --new-window"
CALCULATOR   = "gnome-calculator"

-- Selected by script.sh --profile portable|desktop.
MACHINE = require("config.machine")
MONITOR1 = MACHINE.monitors[1]
MONITOR2 = MACHINE.monitors[2]
MONITOR3 = MACHINE.monitors[3]
PRIMARY_MONITOR = MONITOR1

NUM_WPM = 5 -- Number of workspaces per monitor (Max 10)

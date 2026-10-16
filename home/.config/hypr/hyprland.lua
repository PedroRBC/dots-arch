require("config.variables")
require("config.animations")
require("config.autostart")
require("config.colors")
require("config.decorations")
require("config.inputs")
require("config.binds")
require("config.misc")
require("config.monitors")
require("config.windowrules")

if MACHINE.t3_capture then
    hl.bind("CTRL + SHIFT + 2", hl.dsp.global("com.t3tools.T3Code:capture-window"))
end

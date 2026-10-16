-- Monitor wiki https://wiki.hypr.land/Configuring/Basics/Monitors/
-- Example: output can be found with hyprctl monitors. Edit variables.lua for the monitor outputs instead of here directly
-- hl.monitor({
--     output    = MONITOR1,
--     mode      = "1920x1080@60",
--     position  = "0x0",
--     scale     = "1",
-- })

hl.monitor({
    output    = "DP-2",
    mode      = "1920x1080@240",
    position  = "0x0",
    supports_hdr = 1,
})

hl.monitor({
    output    = "DP-3",
    mode      = "1920x1080@60",
    position  = "-1920x0",
    scale     = "1"
})

hl.monitor({
    output    = "HDMI-A-1",
    mode      = "preferred",
    position  = "auto",
    scale     = "1",
    transform = 3,
})

for i = 1, 5 do
    hl.workspace_rule({
        workspace = tostring(i),
        monitor = "DP-3",
        persistent = true,
    })
end

for i = 6, 10 do
    hl.workspace_rule({
        workspace = tostring(i),
        monitor = "HDMI-A-1",
        persistent = true,
    })
end

for i = 11, 15 do
    hl.workspace_rule({
        workspace = tostring(i),
        monitor = "DP-2",
        persistent = true,
    })
end
-- Existing desktop: explicit opt-in, not defaults for a new computer.
return {
    monitors = { "DP-2", "DP-3", "HDMI-A-1" },
    vrr = 3,
    direct_scanout = 2,
    t3_capture = true,
    -- Preserves the existing X11 policy. Set false if root X11 apps are unnecessary.
    xhost_root = true,
}

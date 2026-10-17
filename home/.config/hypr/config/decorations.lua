-- Look and feel configuration

hl.config({
    general = {
        gaps_in = 3,
        gaps_out = 8,
        border_size = 2,
        extend_border_grab_area = 10,
        resize_on_border = true,
        col = {
            active_border = {
                colors = { ARC_CYAN, ARC_BLUE },
                angle = 45,
            },
            inactive_border = ARC_OUTLINE,
        },
    },
    misc = {
        disable_hyprland_logo    = true,
        disable_splash_rendering = true,
    },
    group = {
        col = {
            border_active = ARC_CYAN,
            border_inactive = ARC_OUTLINE,
            border_locked_active = ARC_AMBER,
            border_locked_inactive = ARC_OUTLINE,
        },
        groupbar = {
            col = {
                active = ARC_CYAN,
                inactive = ARC_OUTLINE,
                locked_active = ARC_AMBER,
                locked_inactive = ARC_OUTLINE,
            },
        },
    },
    decoration = {
        dim_special = 0.3,
        rounding = 6,
        active_opacity = 0.98,
        inactive_opacity = 0.94,
        fullscreen_opacity = 1,
        blur = {
            size = 5,
            passes = 4,
            special = true,
        },
    },
})

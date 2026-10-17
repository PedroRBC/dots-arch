-- Default curves and animations, see https://wiki.hypr.land/Configuring/Advanced-and-Cool/Animations/

-- Default beziers
hl.curve("easeOutQuint",   { type = "bezier", points = { {0.23, 1},    {0.32, 1}    } })
hl.curve("easeInOutCubic", { type = "bezier", points = { {0.65, 0.05}, {0.36, 1}    } })
hl.curve("linear",         { type = "bezier", points = { {0, 0},       {1, 1}       } })
hl.curve("almostLinear",   { type = "bezier", points = { {0.5, 0.5},   {0.75, 1}    } })
hl.curve("quick",          { type = "bezier", points = { {0.15, 0},    {0.1, 1}     } })
hl.curve("overshoot",      { type = "bezier", points = { {0.5, 0.9}, {0.1, 1.1}     } })

-- Default springs
hl.curve("easy",           { type = "spring", mass = 1, stiffness = 500, dampening = 35 })
hl.curve("rubber",         { type = "spring", mass = 1, stiffness = 200,  dampening = 15 })

-- ARC Motion: precise, non-overshooting motion; no new child overrides.
hl.curve("arcOut", { type = "bezier", points = { {0.16, 1}, {0.3, 1} } })
hl.curve("arcIn",  { type = "bezier", points = { {0.4, 0},  {1, 1}   } })

hl.animation({ leaf = "global",              enabled = true, speed = 1.6, bezier = "arcOut"                            })
hl.animation({ leaf = "windows",             enabled = true, speed = 2.2, bezier = "arcOut", style = "popin 97%"       })
hl.animation({ leaf = "workspaces",          enabled = true, speed = 2.0, bezier = "arcOut", style = "slidefade 15%"   })
hl.animation({ leaf = "specialWorkspaceIn",  enabled = true, speed = 1.8, bezier = "arcOut", style = "slide top 15%"   })
hl.animation({ leaf = "specialWorkspaceOut", enabled = true, speed = 1.3, bezier = "arcIn",  style = "slide top 15%"   })

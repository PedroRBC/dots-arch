-- Session started by UWSM; do not start another shell from the installer.
hl.on("hyprland.start", function ()
    hl.exec_cmd("dbus-update-activation-environment --systemd --all")
    hl.exec_cmd("noctalia")
    if MACHINE.xhost_root then
        hl.exec_cmd("xhost +SI:localuser:root")
    end
end)

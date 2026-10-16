if status is-interactive; and test -f /usr/share/cachyos-fish-config/cachyos-config.fish
    source /usr/share/cachyos-fish-config/cachyos-config.fish
end

fish_add_path --global --move "$HOME/.local/bin"

# Bun is optional; do not add missing directories to PATH.
set -gx BUN_INSTALL "$HOME/.bun"
if test -d "$BUN_INSTALL/bin"
    fish_add_path --global "$BUN_INSTALL/bin"
end

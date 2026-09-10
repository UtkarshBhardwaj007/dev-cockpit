local wezterm = require 'wezterm'
local config = wezterm.config_builder()
config.color_scheme = 'Catppuccin Mocha'
config.font = wezterm.font_with_fallback { 'JetBrainsMono Nerd Font', 'Cascadia Code' }
config.font_size = 12.5
config.window_padding = { left = 12, right = 12, top = 10, bottom = 10 }
config.window_background_opacity = 0.97
config.use_fancy_tab_bar = false
config.hide_tab_bar_if_only_one_tab = true
config.default_cursor_style = 'SteadyBlock'
-- Keep the detected shell until PowerShell 7 has been explicitly provisioned.
-- Herdr runs from the `dev` shell function; no automatic nested multiplexer.
return config

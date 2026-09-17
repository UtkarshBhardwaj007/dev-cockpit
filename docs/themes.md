# Themes

## Current theme (Catppuccin Mocha)

The repo applies the Catppuccin Mocha palette across the shell toolchain. Where each piece is configured:

- **yazi** — vendored Catppuccin Mocha (mauve accent) theme from the Catppuccin yazi port (`config/yazi/theme.toml`).
- **starship** — the Catppuccin Powerline preset from the Starship presets gallery (`config/starship/starship.toml`).
- **Ghostty** — built-in `Catppuccin Mocha` terminal theme (`config/terminals/ghostty`).
- **WezTerm** — `Catppuccin Mocha` color scheme (`config/terminals/wezterm.lua`).
- **OMP** — built-in dark/light catppuccin scheme (`config/omp/config.yml`).
- **Herdr** — built-in `catppuccin` scheme (`config/herdr/config.toml`).

Canonical sources to check online:

- Catppuccin: <https://catppuccin.com>
- Catppuccin repo: <https://github.com/catppuccin/catppuccin>
- Starship Catppuccin Powerline preset: <https://starship.rs/presets/catppuccin-powerline.html>
- Catppuccin yazi port: <https://github.com/catppuccin/yazi>

## Alternative theme options

A curated set of popular, "cool/fancy" developer themes to preview. Each is a config-only swap (see note below).

- **Tokyo Night** — deep blue/night palette with neon accents; official repo: <https://github.com/folke/tokyonight.nvim>
- **Dracula** — dark purple/gray base with vivid pink, cyan, and green accents; <https://draculatheme.com>
- **Nord** — arctic, desaturated blue palette with a calm, minimalist feel; <https://nordtheme.com>
- **Rosé Pine** — soft, pastel rose/wood tones for a warm, elegant look; <https://rosepinetheme.com> and repo <https://github.com/rose-pine/rose-pine>
- **Gruvbox** — warm retro palette (dark mode) with earthy orange/yellow tones; <https://github.com/morhetz/gruvbox>
- **Everforest** — soft, muted green/forest palette designed for eye comfort; <https://github.com/sainnhe/everforest>
- **Kanagawa** — muted, Japanese-ink-inspired colors (navy, cream, red); <https://github.com/rebelot/kanagawa.nvim>
- **One Dark** — dark, neutral palette with subtle blue/green accents (Atom's classic); <https://github.com/navarasu/onedark.nvim>

Gallery-style places to preview many schemes at once:

- Starship presets gallery: <https://starship.rs/presets/>
- WezTerm color-scheme gallery: <https://wezfurlong.org/wezterm/colorschemes/>

## Font and how to swap

The font stays **JetBrainsMono Nerd Font** regardless of theme. Swapping the theme is a config-only change — update the theme reference in the relevant config files (`config/yazi`, `config/starship`, `config/terminals`, `config/omp`, `config/herdr`) and reapply/restart the affected tool. No code or vendored-file changes are required beyond the theme source.

# Source from interactive bash/zsh. Optional tools are checked before use.
case $- in *i*) ;; *) return ;; esac
[ -n "${DEV_COCKPIT_INITIALIZED:-}" ] && return
DEV_COCKPIT_INITIALIZED=1
export STARSHIP_CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}/dev-cockpit/starship.toml"
if [ -n "${ZSH_VERSION:-}" ]; then
    command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init zsh)"
    command -v starship >/dev/null 2>&1 && eval "$(starship init zsh)"
elif [ -n "${BASH_VERSION:-}" ]; then
    command -v zoxide >/dev/null 2>&1 && eval "$(zoxide init bash)"
    command -v starship >/dev/null 2>&1 && eval "$(starship init bash)"
fi
dev() {
    if command -v herdr >/dev/null 2>&1; then
        herdr "$@"
    else
        printf '%s\n' 'Herdr is missing. See the cockpit profile and docs/customization.md.' >&2
        return 127
    fi
}

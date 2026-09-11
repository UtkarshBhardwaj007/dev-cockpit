# Source from interactive bash/zsh; setup adds managed profile activation.
case $- in *i*) ;; *) return ;; esac
[ -n "${BASH_VERSION:-}${ZSH_VERSION:-}" ] || return
[ -z "${DEV_COCKPIT_INITIALIZED:-}" ] || return
DEV_COCKPIT_INITIALIZED=1
if [ -z "${DEV_COCKPIT_CONFIG_DIR:-}" ]; then
    if [ -n "${BASH_VERSION:-}" ]; then
        DEV_COCKPIT_CONFIG_DIR=$(dirname -- "${BASH_SOURCE[0]}")
    elif [ -n "${ZSH_VERSION:-}" ]; then
        DEV_COCKPIT_CONFIG_DIR=$(dirname -- "${(%):-%N}")
    else
        return
    fi
fi
[ ! -r "$DEV_COCKPIT_CONFIG_DIR/environment.sh" ] || . "$DEV_COCKPIT_CONFIG_DIR/environment.sh"
# Preserve PATH ordering; append installed directories without duplicates.
for _dc_bin in "${DEV_COCKPIT_USER_HOME:-$HOME}/.local/bin" "${DEV_COCKPIT_USER_HOME:-$HOME}/.bun/bin" "${DEV_COCKPIT_USER_HOME:-$HOME}/.local/share/dev-cockpit/graphify/bin" /opt/homebrew/bin /usr/local/bin /home/linuxbrew/.linuxbrew/bin; do
    if [ -d "$_dc_bin" ]; then
        case ":$PATH:" in *":$_dc_bin:"*) ;; *) PATH="$PATH:$_dc_bin" ;; esac
    fi
done
export PATH
unset _dc_bin
_dev_cockpit() {
    if [ -z "${DEV_COCKPIT_ROOT:-}" ] || [ ! -f "$DEV_COCKPIT_ROOT/bootstrap/cockpit.py" ]; then
        printf '%s\n' 'Dev Cockpit runtime is missing. Rerun setup to repair it.' >&2
        return 127
    fi
    "${DEV_COCKPIT_PYTHON:-python3}" "$DEV_COCKPIT_ROOT/bootstrap/cockpit.py" "$@"
}
# Existing user commands, aliases and functions always win.
command -v dev >/dev/null 2>&1 || function dev { _dev_cockpit launch "$@"; }
command -v dev-doctor >/dev/null 2>&1 || function dev-doctor { _dev_cockpit doctor "$@"; }
command -v dev-update >/dev/null 2>&1 || function dev-update { _dev_cockpit update "$@"; }
command -v dev-uninstall >/dev/null 2>&1 || function dev-uninstall { _dev_cockpit uninstall "$@"; }
command -v dev-memory >/dev/null 2>&1 || function dev-memory { _dev_cockpit memory "$@"; }
command -v dev-graph >/dev/null 2>&1 || function dev-graph { _dev_cockpit graph "$@"; }
command -v dev-completions >/dev/null 2>&1 || function dev-completions { _dev_cockpit completions "$@"; }
if command -v eza >/dev/null 2>&1; then
    command -v ll >/dev/null 2>&1 || function ll { eza --long --group-directories-first --git --icons=auto "$@"; }
    command -v lt >/dev/null 2>&1 || function lt { eza --tree --level=2 --icons=auto "$@"; }
fi
if command -v lazygit >/dev/null 2>&1; then
    command -v lg >/dev/null 2>&1 || function lg { lazygit "$@"; }
fi
if command -v delta >/dev/null 2>&1; then
    command -v dg >/dev/null 2>&1 || function dg { git -c "include.path=$DEV_COCKPIT_CONFIG_DIR/delta.gitconfig" "$@"; }
fi
if command -v yazi >/dev/null 2>&1; then
    command -v y >/dev/null 2>&1 || function y {
        local _dc_tmp _dc_cwd _dc_status
        _dc_tmp=$(mktemp "${TMPDIR:-/tmp}/dev-cockpit-yazi.XXXXXXXX") || return
        yazi "$@" --cwd-file="$_dc_tmp"
        _dc_status=$?
        if [ -s "$_dc_tmp" ]; then
            IFS= read -r _dc_cwd < "$_dc_tmp" || :
            [ -z "$_dc_cwd" ] || [ ! -d "$_dc_cwd" ] || builtin cd -- "$_dc_cwd" || :
        fi
        rm -f -- "$_dc_tmp"
        return "$_dc_status"
    }
fi
# Catppuccin Mocha, applied only when no user options were set.
: "${FZF_DEFAULT_OPTS=--height=60% --layout=reverse --border --color=bg+:#313244,bg:#1e1e2e,fg:#cdd6f4,fg+:#cdd6f4,hl:#f38ba8,hl+:#f38ba8,pointer:#f5e0dc,marker:#b4befe,spinner:#f5e0dc,header:#f38ba8,info:#cba6f7,prompt:#cba6f7}"
export FZF_DEFAULT_OPTS
if command -v fd >/dev/null 2>&1; then
    : "${FZF_DEFAULT_COMMAND=fd --type f --hidden --exclude .git}"
    : "${FZF_CTRL_T_COMMAND=$FZF_DEFAULT_COMMAND}"
    export FZF_DEFAULT_COMMAND FZF_CTRL_T_COMMAND
fi
if [ -n "${ZSH_VERSION:-}" ]; then
    _dc_shell=zsh
    for _dc_fpath in "$DEV_COCKPIT_CONFIG_DIR/completions/zsh" /opt/homebrew/share/zsh/site-functions /usr/local/share/zsh/site-functions /home/linuxbrew/.linuxbrew/share/zsh/site-functions; do
        if [ -d "$_dc_fpath" ] && (( ${fpath[(Ie)$_dc_fpath]} == 0 )); then
            fpath=("$_dc_fpath" "${fpath[@]}")
        fi
    done
    if ! command -v compdef >/dev/null 2>&1; then
        autoload -Uz compinit
        # Ignore insecure directories; do not weaken compinit's security checks.
        compinit -i -D
    fi
    # Register new completions even if the existing profile ran compinit.
    # Use a shell-independent glob loop so Bash can parse this file, too.
    for _dc_tool in gh herdr omp starship; do
        _dc_completion="$DEV_COCKPIT_CONFIG_DIR/completions/zsh/_$_dc_tool"
        [ -f "$_dc_completion" ] || continue
        _dc_name=${_dc_completion##*/}
        autoload -Uz "$_dc_name"
        compdef "$_dc_name" "${_dc_name#_}"
    done
    unset _dc_fpath _dc_name _dc_tool
elif [ -n "${BASH_VERSION:-}" ]; then
    _dc_shell=bash
    if [ -z "${BASH_COMPLETION_VERSINFO:-}" ]; then
        for _dc_completion in /opt/homebrew/etc/profile.d/bash_completion.sh /usr/local/etc/profile.d/bash_completion.sh /home/linuxbrew/.linuxbrew/etc/profile.d/bash_completion.sh /usr/share/bash-completion/bash_completion; do
            if [ -r "$_dc_completion" ] && [ "${BASH_VERSINFO[0]}" -ge 4 ]; then . "$_dc_completion"; break; fi
        done
    fi
    # Apple's Bash 3.2 cannot load bash-completion v2 but can load Git's script.
    if ! declare -F __git_complete >/dev/null 2>&1; then
        for _dc_completion in /opt/homebrew/etc/bash_completion.d/git-completion.bash /usr/local/etc/bash_completion.d/git-completion.bash /home/linuxbrew/.linuxbrew/etc/bash_completion.d/git-completion.bash /usr/share/git-core/contrib/completion/git-completion.bash /usr/share/bash-completion/completions/git; do
            if [ -r "$_dc_completion" ]; then . "$_dc_completion"; break; fi
        done
    fi
    for _dc_completion in "$DEV_COCKPIT_CONFIG_DIR"/completions/bash/*.bash; do
        [ ! -r "$_dc_completion" ] || . "$_dc_completion"
    done
else
    return
fi
unset _dc_completion
if command -v fzf >/dev/null 2>&1 && [ "${DEV_COCKPIT_SKIP_FZF:-0}" != 1 ]; then
    # Atuin takes Ctrl-R below; fzf supplies Ctrl-T, Alt-C and **<Tab>.
    _dc_hook=$(fzf "--$_dc_shell" 2>/dev/null) && eval "$_dc_hook"
fi
if command -v zoxide >/dev/null 2>&1 && [ "${DEV_COCKPIT_SKIP_ZOXIDE:-0}" != 1 ] && ! command -v __zoxide_z >/dev/null 2>&1; then
    _dc_hook=$(zoxide init "$_dc_shell" 2>/dev/null) && eval "$_dc_hook"
fi
if command -v mise >/dev/null 2>&1 && [ "${DEV_COCKPIT_SKIP_MISE:-0}" != 1 ] && ! command -v _mise_hook >/dev/null 2>&1; then
    _dc_hook=$(mise activate "$_dc_shell" 2>/dev/null) && eval "$_dc_hook"
fi
if command -v direnv >/dev/null 2>&1 && [ "${DEV_COCKPIT_SKIP_DIRENV:-0}" != 1 ] && ! command -v _direnv_hook >/dev/null 2>&1; then
    _dc_hook=$(direnv hook "$_dc_shell" 2>/dev/null) && eval "$_dc_hook"
fi
if command -v atuin >/dev/null 2>&1 && [ "${DEV_COCKPIT_SKIP_ATUIN:-0}" != 1 ] && ! command -v _atuin_preexec >/dev/null 2>&1; then
    _dc_hook=$(atuin init "$_dc_shell" --disable-up-arrow 2>/dev/null) && eval "$_dc_hook"
fi
if command -v starship >/dev/null 2>&1 && [ "${DEV_COCKPIT_SKIP_STARSHIP:-0}" != 1 ] && [ -z "${STARSHIP_SESSION_KEY:-}" ]; then
    if [ -z "${STARSHIP_CONFIG:-}" ] && [ ! -f "${XDG_CONFIG_HOME:-$HOME/.config}/starship.toml" ]; then
        export STARSHIP_CONFIG="$DEV_COCKPIT_CONFIG_DIR/starship.toml"
    fi
    _dc_hook=$(starship init "$_dc_shell" 2>/dev/null) && eval "$_dc_hook"
fi
if [ "$_dc_shell" = zsh ]; then
    if [ "${DEV_COCKPIT_SKIP_SUGGESTIONS:-0}" != 1 ] && ! command -v _zsh_autosuggest_start >/dev/null 2>&1; then
        for _dc_plugin in /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh /usr/local/share/zsh-autosuggestions/zsh-autosuggestions.zsh /home/linuxbrew/.linuxbrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh; do
            if [ -r "$_dc_plugin" ]; then . "$_dc_plugin"; break; fi
        done
    fi
    # Syntax highlighting loads last, after other widgets and integrations.
    if [ "${DEV_COCKPIT_SKIP_HIGHLIGHTING:-0}" != 1 ] && ! command -v _zsh_highlight >/dev/null 2>&1; then
        for _dc_plugin in /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh /usr/local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh /home/linuxbrew/.linuxbrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh; do
            if [ -r "$_dc_plugin" ]; then . "$_dc_plugin"; break; fi
        done
    fi
    unset _dc_plugin
fi
unset _dc_hook _dc_shell
# Missing or old optional integrations never make profile initialization fail.
:

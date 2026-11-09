# Shared prompt for interactive Bash on macOS and Linux.
case $- in
  *i*) ;;
  *) return ;;
esac

alias y='yazi'

# Find user-installed Starship and Homebrew without depending on the parent shell.
for bin_dir in /usr/local/bin /opt/homebrew/bin "$HOME/.local/bin"; do
  if [ -d "$bin_dir" ]; then
    case ":$PATH:" in
      *":$bin_dir:"*) ;;
      *) PATH="$bin_dir:$PATH" ;;
    esac
  fi
done
export PATH

# Keep machine-specific Bash settings outside the public repository.
if [ -r "$HOME/.bashrc.local" ]; then
  . "$HOME/.bashrc.local"
fi

# Option on macOS / Alt on Linux: move by words in Emacs and Vi modes.
for terminal_dotfiles_keymap in emacs-standard vi-insert vi-command; do
  bind -m "$terminal_dotfiles_keymap" '"\e[1;3D": backward-word'
  bind -m "$terminal_dotfiles_keymap" '"\e[1;3C": forward-word'
done
unset terminal_dotfiles_keymap

# Match Zsh: ordinary SSH uses compatible terminfo on every destination.
# Leave the local terminal's TERM unchanged.
ssh() {
  TERM=xterm-256color command ssh "$@"
}

if command -v zoxide >/dev/null 2>&1; then
  eval "$(zoxide init bash)"
fi

if command -v starship >/dev/null 2>&1; then
  eval "$(starship init bash)"
fi

# Publish local prompt state explicitly, including shells nested by Kubie.
if [[ -n ${KITTY_WINDOW_ID-} && -z ${SSH_TTY-}${SSH_CONNECTION-} ]]; then
  _terminal_dotfiles_publish_state() {
    local phase=$1 program=${2-} directory=$PWD context=${_terminal_dotfiles_kube_label-} encoded
    directory=${directory//[[:cntrl:]]/}
    program=${program//[[:cntrl:]]/}
    directory=${directory//\\/\\\\}; directory=${directory//\"/\\\"}
    context=${context//\\/\\\\}; context=${context//\"/\\\"}
    context=${context//$'\033'/\\u001b}; context=${context//[[:cntrl:]]/}
    program=${program//\\/\\\\}; program=${program//\"/\\\"}
    encoded=$(printf '{"v":1,"pid":%s,"phase":"%s","cwd":"%s","context":"%s","command":"%s","kube_env":"%s"}' \
      "$$" "$phase" "$directory" "$context" "$program" "${_terminal_dotfiles_kube_env-}" | command base64 | command tr -d '\r\n')
    printf '\033]1337;SetUserVar=terminal_dotfiles_state=%s\007' "$encoded"
  }
  _terminal_dotfiles_kubie_title() {
    local previous_status=$? current_context
    _terminal_dotfiles_kube_label=''
    _terminal_dotfiles_kube_env=''
    if [[ -n ${KUBIE_ACTIVE-} ]] && command -v starship >/dev/null 2>&1; then
      _terminal_dotfiles_kube_label=$(command starship module kubernetes 2>/dev/null)
      if [[ -n $_terminal_dotfiles_kube_label && ${KUBECONFIG-} == "${KUBIE_KUBECONFIG:-${KUBECONFIG-}}" ]] &&
         current_context=$(command kubie info ctx 2>/dev/null); then
        case $current_context in
          dev:?*|dev/?*) _terminal_dotfiles_kube_env=DEV ;;
          test:?*|test/?*) _terminal_dotfiles_kube_env=TEST ;;
          prod:?*|prod/?*) _terminal_dotfiles_kube_env=PROD ;;
          ?*) _terminal_dotfiles_kube_env='?ENV' ;;
        esac
      fi
    fi
    _terminal_dotfiles_publish_state prompt
    return "$previous_status"
  }
  _terminal_dotfiles_tab_command() {
    local line program
    line=$(HISTTIMEFORMAT='' builtin history 1)
    line=${line#*[[:digit:]]*[[:space:]]}
    line=${line#"${line%%[![:space:]]*}"}
    program=${line%%[[:space:]]*}
    _terminal_dotfiles_publish_state running "${program##*/}"
  }
  if [[ ${PROMPT_COMMAND[*]-} != *'_terminal_dotfiles_kubie_title'* ]]; then
    if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == 'declare -a '* ]]; then
      PROMPT_COMMAND+=(_terminal_dotfiles_kubie_title)
    else
      # PROMPT_COMMAND is a scalar in this branch (also on macOS Bash 3.2).
      # shellcheck disable=SC2178,SC2128
      PROMPT_COMMAND="${PROMPT_COMMAND:+${PROMPT_COMMAND[0]}; }_terminal_dotfiles_kubie_title"
    fi
  fi
  if (( BASH_VERSINFO[0] > 4 || BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 4 )) &&
     [[ ${PS0-} != *'_terminal_dotfiles_tab_command'* ]]; then
    PS0+='$( _terminal_dotfiles_tab_command )'
  fi
fi

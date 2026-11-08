# Shared prompt for interactive Bash on macOS and Linux.
case $- in
  *i*) ;;
  *) return ;;
esac

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

# Publish the same Kubernetes text as the prompt, scoped to this shell PID.
if [[ -n ${KITTY_WINDOW_ID-} ]]; then
  _terminal_dotfiles_kubie_title() {
    local previous_status=$? label encoded=
    if [[ -n ${KUBIE_ACTIVE-} ]] && command -v starship >/dev/null 2>&1; then
      label=$(command starship module kubernetes 2>/dev/null | command sed -E $'s/\033\\[[0-9;:]*m//g')
      if [[ -n $label ]]; then
        encoded=$(printf '%s' "$$|$label" | command base64 | command tr -d '\r\n')
      fi
    fi
    # Empty metadata clears a context when returning from a nested Kubie shell.
    printf '\033]1337;SetUserVar=terminal_dotfiles_kubie=%s\007' "$encoded"
    return "$previous_status"
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
fi

# Remote title reporting for plain SSH, without replacing an existing DEBUG trap.
if [[ -n ${SSH_TTY-}${SSH_CONNECTION-} ]] &&
   [[ ${TERM-} == xterm* || ${TERM-} == screen* || ${TERM-} == tmux* ]]; then
  _terminal_dotfiles_remote_title() {
    local previous_status=$? location=$PWD host=${HOSTNAME%%.*} command_name='' title
    [[ $location == "$HOME" ]] && location='~'
    (( EUID == 0 )) && host="root@$host"
    if [[ -n ${1-} ]]; then
      command_name=${1#"${1%%[![:space:]]*}"}
      command_name=${command_name%%[[:space:]]*}
      command_name=${command_name##*/}
    fi
    title="$host: $location${command_name:+ · $command_name}"
    printf '\033]2;%s\007' "${title//[[:cntrl:]]/}"
    return "$previous_status"
  }
  _terminal_dotfiles_remote_preexec() {
    local last_command
    last_command=$(HISTTIMEFORMAT='' builtin history 1)
    last_command=${last_command#*[[:digit:]]*[[:space:]]}
    _terminal_dotfiles_remote_title "$last_command"
  }
  if [[ ${PROMPT_COMMAND[*]-} != *'_terminal_dotfiles_remote_title'* ]]; then
    if [[ $(declare -p PROMPT_COMMAND 2>/dev/null) == 'declare -a '* ]]; then
      PROMPT_COMMAND+=(_terminal_dotfiles_remote_title)
    else
      # shellcheck disable=SC2178,SC2128
      PROMPT_COMMAND="${PROMPT_COMMAND:+${PROMPT_COMMAND[0]}; }_terminal_dotfiles_remote_title"
    fi
  fi
  # PS0 runs before each command in Bash 4.4+. Bash 3.2 still reports the directory.
  if (( BASH_VERSINFO[0] > 4 || BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 4 )) &&
     [[ ${PS0-} != *'_terminal_dotfiles_remote_preexec'* ]]; then
    PS0+='$( _terminal_dotfiles_remote_preexec )'
  fi
fi

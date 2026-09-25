# SSH policy for interactive Kitty sessions. The managed list is private and
# empty by default; a matching entry permits the SSH kitten to prepare the
# remote user's home directory. All other hosts use standard xterm terminfo.
function ssh() {
  emulate -L zsh
  local managed_file="$HOME/.config/terminal-dotfiles/managed-ssh-hosts"

  if [[ -z ${KITTY_WINDOW_ID-} || ! -t 0 || ! -t 1 ]]; then
    command ssh "$@"
    return $?
  fi

  # Queries and forwarding do not open a remote interactive terminal.
  local ssh_arg
  for ssh_arg in "$@"; do
    case $ssh_arg in
      -G|-V|-Q|-T|-N|-W|-O)
        command ssh "$@"
        return $?
        ;;
    esac
  done

  local identity=''
  if [[ -s $managed_file ]]; then
    # -G resolves aliases and command-line user/port without connecting.
    identity=$(command ssh -G "$@" 2>/dev/null | awk '
      $1 == "user" { user = $2 }
      $1 == "hostname" { hostname = $2 }
      $1 == "port" { port = $2 }
      END {
        if (user != "" && hostname != "" && port != "")
          print user "@" hostname ":" port
      }
    ')
    if [[ -n $identity ]] && LC_ALL=C grep -Fqx -- "$identity" "$managed_file"; then
      local kitten_exe=''
      if (( $+commands[kitten] )); then
        kitten_exe=$commands[kitten]
      elif [[ -x /Applications/kitty.app/Contents/MacOS/kitten ]]; then
        kitten_exe=/Applications/kitty.app/Contents/MacOS/kitten
      elif [[ -x $HOME/.local/kitty.app/bin/kitten ]]; then
        kitten_exe=$HOME/.local/kitty.app/bin/kitten
      fi
      if [[ -z $kitten_exe ]]; then
        print -u2 -- 'SSH kitten not found for a managed host'
        return 127
      fi
      "$kitten_exe" ssh "$@"
      return $?
    fi
  fi

  TERM=xterm-256color command ssh "$@"
}

# SSH policy for interactive Kitty sessions. Host globs are private and
# absent by default; a matching rule permits the SSH kitten to prepare the
# remote user's home directory. Other hosts use standard xterm terminfo.
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

  local hostname=''
  if [[ -s $managed_file ]]; then
    # -G resolves HostName and aliases without connecting to the host.
    hostname=$(command ssh -G "$@" 2>/dev/null | awk '$1 == "hostname" { print $2; exit }')
    if [[ -n $hostname ]] && awk -v host="$hostname" '
      function glob_to_regex(glob, regex, i, c) {
        regex = "^"
        for (i = 1; i <= length(glob); i++) {
          c = substr(glob, i, 1)
          if (c == "*") regex = regex ".*"
          else if (c == "?") regex = regex "."
          else if (c == "." || c == "^" || c == "$" || c == "[" ||
                   c == "]" || c == "(" || c == ")" || c == "{" ||
                   c == "}" || c == "+" || c == "|" || c == "\\")
            regex = regex "\\" c
          else regex = regex c
        }
        return regex "$"
      }
      BEGIN { host = tolower(host); managed = 0 }
      {
        rule = $0
        sub(/\r$/, "", rule)
        sub(/^[ \t]+/, "", rule)
        sub(/[ \t]+$/, "", rule)
        if (rule == "" || substr(rule, 1, 1) == "#") next
        excluded = substr(rule, 1, 1) == "!"
        if (excluded) rule = substr(rule, 2)
        if (rule != "" && host ~ glob_to_regex(tolower(rule)))
          managed = excluded ? 0 : 1
      }
      END { exit(managed ? 0 : 1) }
    ' "$managed_file"; then
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
      "$kitten_exe" ssh --kitten env=force_color_prompt=yes "$@"
      return $?
    fi
  fi

  TERM=xterm-256color command ssh "$@"
}

# Shared interactive zsh setup for macOS and Linux.
# Host-specific PATH and aliases belong in ~/.zshrc.local.

alias k='kubectl'
alias y='yazi'

# Make user-installed tools and Homebrew visible before initialization.
typeset -U path
for bin_dir in /usr/local/bin /opt/homebrew/bin "$HOME/.local/bin"; do
  [[ -d "$bin_dir" ]] && path=("$bin_dir" $path)
done
[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"

# Native completion. Homebrew completions are optional on Linux.
for completion_dir in /opt/homebrew/share/zsh/site-functions /usr/local/share/zsh/site-functions; do
  [[ -d $completion_dir ]] && fpath=($completion_dir $fpath)
done
autoload -Uz compinit
compinit

# Fn+Left/Right on macOS send Home/End. Keep these keys usable without a
# framework, even when xterm-kitty terminfo is unavailable on the host.
for keymap in emacs viins vicmd; do
  bindkey -M "$keymap" $'\e[H' beginning-of-line
  bindkey -M "$keymap" $'\eOH' beginning-of-line
  bindkey -M "$keymap" $'\e[F' end-of-line
  bindkey -M "$keymap" $'\eOF' end-of-line
  bindkey -M "$keymap" $'\e[5~' up-line-or-history
  bindkey -M "$keymap" $'\e[6~' down-line-or-history
  # Option on macOS / Alt on Linux: match Readline word movement.
  bindkey -M "$keymap" $'\e[1;3D' emacs-backward-word
  bindkey -M "$keymap" $'\e[1;3C' emacs-forward-word
done

# Directory jumping with zoxide defaults: z and zi.
if (( $+commands[zoxide] )); then
  eval "$(zoxide init zsh)"
fi

# Prompt shared by all terminals and both operating systems.
if (( $+commands[starship] )); then
  eval "$(starship init zsh)"
fi

# Publish a complete local shell snapshot; nested Kubie shells have no native
# Kitty prompt/command hooks. Never install this protocol on remote SSH shells.
if [[ -n ${KITTY_WINDOW_ID-} && -z ${SSH_TTY-}${SSH_CONNECTION-} ]]; then
  _terminal_dotfiles_publish_state() {
    local phase=$1 program=${2-} directory=$PWD context=${_terminal_dotfiles_kube_label-} encoded
    local namespace=${_terminal_dotfiles_kube_namespace-}
    directory=${directory//[[:cntrl:]]/}
    program=${program//[[:cntrl:]]/}
    directory=${directory//\\/\\\\}; directory=${directory//\"/\\\"}
    context=${context//\\/\\\\}; context=${context//\"/\\\"}
    context=${context//$'\033'/\\u001b}; context=${context//[[:cntrl:]]/}
    program=${program//\\/\\\\}; program=${program//\"/\\\"}
    namespace=${namespace//\\/\\\\}; namespace=${namespace//\"/\\\"}
    namespace=${namespace//[[:cntrl:]]/}
    encoded=$(printf '{"v":1,"pid":%s,"phase":"%s","cwd":"%s","context":"%s","command":"%s","kube_env":"%s","kube_color":"%s","kube_category":"%s","kube_namespace":"%s"}' \
      "$$" "$phase" "$directory" "$context" "$program" "${_terminal_dotfiles_kube_env-}" "${_terminal_dotfiles_kube_color-}" "${_terminal_dotfiles_kube_category-}" "$namespace" | command base64 | command tr -d '\r\n')
    printf '\033]1337;SetUserVar=terminal_dotfiles_state=%s\007' "$encoded"
  }
  _terminal_dotfiles_kubie_title() {
    typeset -g _terminal_dotfiles_kube_label='' _terminal_dotfiles_kube_env=''
    _terminal_dotfiles_kube_color=''
    _terminal_dotfiles_kube_category=''
    _terminal_dotfiles_kube_namespace=''
    if [[ -n ${KUBIE_ACTIVE-} && -x "$HOME/.config/terminal-dotfiles/kube-environment" ]]; then
      local metadata
      metadata=$("$HOME/.config/terminal-dotfiles/kube-environment" --state --with-category 2>/dev/null)
      if [[ -n $metadata ]]; then
        IFS=$'\t' read -r _terminal_dotfiles_kube_env _terminal_dotfiles_kube_color _terminal_dotfiles_kube_label <<< "$metadata"
        if [[ $metadata == *$'\n'* ]]; then
          IFS=$'\t' read -r _terminal_dotfiles_kube_category _terminal_dotfiles_kube_namespace <<< "${metadata#*$'\n'}"
        fi
      fi
    fi
    _terminal_dotfiles_publish_state prompt
    return 0
  }
  _terminal_dotfiles_tab_command() {
    local -a words
    local program
    words=(${(z)1})
    while (( $#words )) && [[ ${words[1]} =~ '^[A-Za-z_][A-Za-z_0-9]*=' || ${words[1]} == (command|exec) ]]; do
      shift words
    done
    program=${(Q)words[1]}
    _terminal_dotfiles_publish_state running "${program:t}"
    return 0
  }
  autoload -Uz add-zsh-hook
  add-zsh-hook precmd _terminal_dotfiles_kubie_title
  add-zsh-hook preexec _terminal_dotfiles_tab_command
fi

# Use compatible terminfo for every SSH destination.
[[ -r "$HOME/.config/terminal-dotfiles/ssh.zsh" ]] && source "$HOME/.config/terminal-dotfiles/ssh.zsh"

# Small zsh features without a plugin framework.
for plugin_file in /opt/homebrew/share/zsh-autosuggestions/zsh-autosuggestions.zsh /usr/local/share/zsh-autosuggestions/zsh-autosuggestions.zsh /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh; do
  if [[ -r $plugin_file ]]; then
    source "$plugin_file"
    break
  fi
done

# Optional host-specific overrides; keep this file outside the public repo.
# Load before syntax highlighting, which should remain last.
[[ -r "$HOME/.zshrc.local.post" ]] && source "$HOME/.zshrc.local.post"

for plugin_file in /opt/homebrew/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh /usr/local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh; do
  if [[ -r $plugin_file ]]; then
    source "$plugin_file"
    break
  fi
done

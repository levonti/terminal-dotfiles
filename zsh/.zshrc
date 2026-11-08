# Shared interactive zsh setup for macOS and Linux.
# Host-specific PATH and aliases belong in ~/.zshrc.local.

alias k='kubectl'

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

# Publish the same Kubernetes text as the prompt, scoped to this shell PID.
# Starship reads the local kubeconfig; no Kubernetes API calls are needed.
if [[ -n ${KITTY_WINDOW_ID-} ]]; then
  _terminal_dotfiles_kubie_title() {
    local label encoded=
    if [[ -n ${KUBIE_ACTIVE-} ]] && (( $+commands[starship] )); then
      label=$(command starship module kubernetes 2>/dev/null | command sed -E $'s/\033\\[[0-9;:]*m//g')
      if [[ -n $label ]]; then
        encoded=$(printf '%s' "$$|$label" | command base64 | command tr -d '\r\n')
      fi
    fi
    # Clear on every outer-shell prompt as well, including after `exit`.
    printf '\033]1337;SetUserVar=terminal_dotfiles_kubie=%s\007' "$encoded"
    return 0
  }
  autoload -Uz add-zsh-hook
  add-zsh-hook precmd _terminal_dotfiles_kubie_title
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

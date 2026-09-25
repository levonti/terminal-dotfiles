# Shared interactive zsh setup for macOS and Linux.
# Host-specific PATH and aliases belong in ~/.zshrc.local.

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
done

# Directory jumping with zoxide defaults: z and zi.
if (( $+commands[zoxide] )); then
  eval "$(zoxide init zsh)"
fi

# Prompt shared by all terminals and both operating systems.
if (( $+commands[starship] )); then
  eval "$(starship init zsh)"
fi

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

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

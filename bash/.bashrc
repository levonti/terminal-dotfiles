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

if command -v starship >/dev/null 2>&1; then
  eval "$(starship init bash)"
fi

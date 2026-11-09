#!/bin/sh
# Install the Zsh, Kitty and Starship packages over an existing setup.
set -efu

fail() {
  printf '%s\n' "$*" >&2
  exit 1
}

case ${1-} in
  --check|--migrate) [ "$#" -eq 1 ] || fail 'Usage: sh scripts/install.sh --check|--migrate' ;;
  *) fail 'Usage: sh scripts/install.sh --check|--migrate' ;;
esac

command -v stow >/dev/null 2>&1 || fail 'GNU Stow is required; on Ubuntu run: sudo apt install stow'
repo_dir=$(CDPATH='' cd "$(dirname "$0")/.." && pwd -P)
target_home=$(CDPATH='' cd "${HOME:?HOME is required}" && pwd -P)
case "$target_home/" in
  "$repo_dir/"*) fail 'HOME must be outside the dotfiles checkout.' ;;
esac

check_config_dir() {
  # dash and Bash support -ef for comparing directories through symlinks.
  # shellcheck disable=SC3013
  if [ "${2%/}" != "$3" ] && [ ! "$2" -ef "$3" ]; then
    fail "$1 selects '$2'; this installer targets '$3'."
  fi
}

expand_kitty_path() {
  case "$1" in
    '~') printf '%s\n' "$target_home" ;;
    \~/*) printf '%s/%s\n' "$target_home" "${1#*/}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

check_config_dir ZDOTDIR "${ZDOTDIR-$target_home}" "$target_home"
kitty_dir="$target_home/.config/kitty"
if [ -n "${KITTY_CONFIG_DIRECTORY-}" ]; then
  check_config_dir KITTY_CONFIG_DIRECTORY "$(expand_kitty_path "$KITTY_CONFIG_DIRECTORY")" "$kitty_dir"
elif [ -n "${XDG_CONFIG_HOME-}" ]; then
  xdg_kitty_dir="$(expand_kitty_path "$XDG_CONFIG_HOME")/kitty"
  if [ -e "$xdg_kitty_dir/kitty.conf" ]; then
    check_config_dir XDG_CONFIG_HOME "$xdg_kitty_dir" "$kitty_dir"
  fi
fi

# Fixed relative paths, so word splitting is intentional. Inspect parents
# before children and keep unrelated files out of the Stow operation.
config_dirs='.config .config/kitty .config/terminal-dotfiles'
managed='zsh/.zshrc zsh/.config/terminal-dotfiles/ssh.zsh kitty/.config/kitty/kitty.conf kitty/.config/kitty/tab_bar.py starship/.config/starship.toml'
compiled_rc="$target_home/.zshrc.zwc"
pending=
originals=
new_dirs=
backup_dir=
applying=0

installed_link() {
  # dash and Bash support -ef for checking the symlink's target.
  # shellcheck disable=SC3013
  [ -L "$target_home/${1#*/}" ] && [ "$target_home/${1#*/}" -ef "$repo_dir/$1" ]
}

safe_parents() {
  case $1 in
    .config/*) [ ! -L "$target_home/.config" ] && [ ! -L "$target_home/${1%/*}" ] ;;
  esac
}

require_writable_dir() {
  parent=$1
  while [ ! -d "$parent" ]; do
    parent=${parent%/*}
  done
  if [ ! -w "$parent" ] || [ ! -x "$parent" ]; then
    fail "Need write and search permissions on $parent."
  fi
}

rollback() {
  if [ "$applying" -eq 1 ]; then
    for entry in $pending; do
      relative=${entry#*/}
      if ! safe_parents "$relative"; then
        printf 'Cannot roll back %s: a parent is now a symlink.\n' "$target_home/$relative" >&2
      elif installed_link "$entry"; then
        rm "$target_home/$relative"
      fi
    done
    for dir in $new_dirs; do
      if safe_parents "$dir"; then
        rmdir "$target_home/$dir" 2>/dev/null || :
      fi
    done
  fi
  if [ -n "$backup_dir" ]; then
    for relative in $originals; do
      [ -f "$backup_dir/$relative" ] || continue
      target="$target_home/$relative"
      if ! safe_parents "$relative"; then
        printf 'Cannot restore %s: a parent is now a symlink.\n' "$target" >&2
      elif [ ! -e "$target" ] && [ ! -L "$target" ]; then
        mv "$backup_dir/$relative" "$target"
      else
        printf 'Cannot restore %s: the path is occupied.\n' "$target" >&2
      fi
    done
    rmdir "$backup_dir/.config/terminal-dotfiles" "$backup_dir/.config/kitty" \
      "$backup_dir/.config" "$backup_dir" 2>/dev/null || :
    if [ -d "$backup_dir" ]; then
      printf 'Remaining backups: %s\n' "$backup_dir" >&2
    fi
  fi
}

finish() {
  trap '' HUP INT TERM
  set +e
  if [ "$1" -ne 0 ]; then
    rollback
  fi
  rmdir "$lock_dir"
  exit "$1"
}

require_writable_dir "$target_home"
if [ "$1" = --migrate ]; then
  lock_dir="$target_home/.terminal-dotfiles-install.lock"
  mkdir -m 700 "$lock_dir" || fail "Cannot acquire migration lock: $lock_dir"
  trap 'finish "$?"' 0
  trap 'exit 129' HUP
  trap 'exit 130' INT
  trap 'exit 143' TERM
fi

for dir in $config_dirs; do
  path="$target_home/$dir"
  if [ -L "$path" ] || { [ -e "$path" ] && [ ! -d "$path" ]; }; then
    fail "Expected a real directory at $path. Resolve this conflict before migrating."
  fi
  if [ ! -d "$path" ]; then
    new_dirs="$dir $new_dirs"
  fi
done

allowed="$config_dirs"
for entry in $managed; do
  [ -f "$repo_dir/$entry" ] || fail "Missing configuration file: $repo_dir/$entry"
  relative=${entry#*/}
  target="$target_home/$relative"
  if installed_link "$entry"; then
    printf 'Already linked: %s\n' "$target"
    continue
  fi
  if [ -L "$target" ] || { [ -e "$target" ] && [ ! -f "$target" ]; }; then
    fail "Unexpected file type or symlink at $target. Resolve this conflict before migrating."
  fi
  require_writable_dir "${target%/*}"
  if [ -f "$target" ]; then
    printf 'Back up and link: %s\n' "$target"
    originals="$originals $relative"
  else
    printf 'Create link: %s\n' "$target"
  fi
  pending="$pending $entry"
  allowed="$allowed $relative"
done

if [ -L "$compiled_rc" ] || { [ -e "$compiled_rc" ] && [ ! -f "$compiled_rc" ]; }; then
  fail "Expected a regular file at $compiled_rc. Resolve this conflict before migrating."
fi
if [ -f "$compiled_rc" ]; then
  printf 'Back up compiled Zsh configuration: %s\n' "$compiled_rc"
  originals="$originals .zshrc.zwc"
fi

if [ "$1" = --check ]; then
  printf '%s\n' 'Preflight passed. Run with --migrate to apply this plan.'
  exit 0
fi

if [ -n "$originals" ]; then
  backup_dir=$(mktemp -d "$target_home/.terminal-dotfiles-backup.XXXXXXXX")
  for relative in $originals; do
    mkdir -p "$backup_dir/$(dirname "$relative")"
    mv "$target_home/$relative" "$backup_dir/$relative"
  done
fi

if [ -n "$pending" ]; then
  # Ignore local Stow defaults (including --simulate and --adopt).
  # Restrict the operation to the paths covered by rollback.
  allowed=$(printf '%s\n' "$allowed" | sed 's/\./\\./g; s/ /|/g')
  set -- --dir="$repo_dir" --target="$target_home" --no-folding "--ignore=(?s)^(?!($allowed)\z).*" zsh kitty starship
  (cd "$lock_dir" && HOME="$lock_dir" stow --simulate "$@")
  applying=1
  (cd "$lock_dir" && HOME="$lock_dir" stow "$@")
fi

for entry in $managed; do
  installed_link "$entry" || fail "Stow did not create the expected symlink: $target_home/${entry#*/}"
done
if [ -e "$compiled_rc" ] || [ -L "$compiled_rc" ]; then
  fail "Unexpected compiled Zsh configuration at $compiled_rc."
fi
if [ -n "$backup_dir" ]; then
  printf 'Original files saved in %s\n' "$backup_dir"
fi
printf '%s\n' 'Zsh, Kitty and Starship configuration installed.'

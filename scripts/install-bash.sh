#!/bin/sh
# Install the same Bash prompt on macOS and Linux without discarding ~/.bashrc.
set -eu

repo_dir=$(CDPATH= cd "$(dirname "$0")/.." && pwd -P)
target_home=${HOME:?HOME is required}
rc="$target_home/.bashrc"
local_rc="$target_home/.bashrc.local"
moved=0

if ! command -v stow >/dev/null 2>&1; then
  printf '%s\n' 'GNU Stow is required; install it before running this script.' >&2
  exit 1
fi

restore_rc() {
  if [ "$moved" -eq 1 ] && [ ! -e "$rc" ] && [ ! -L "$rc" ]; then
    mv "$local_rc" "$rc"
  fi
}
trap restore_rc 0

if [ -e "$rc" ] && [ ! -L "$rc" ]; then
  if [ ! -f "$rc" ]; then
    printf '%s\n' 'Expected ~/.bashrc to be a regular file or symlink.' >&2
    exit 1
  fi
  if [ -e "$local_rc" ] || [ -L "$local_rc" ]; then
    printf '%s\n' 'Both ~/.bashrc and ~/.bashrc.local exist; resolve this manually before installing Bash.' >&2
    exit 1
  fi
  mv "$rc" "$local_rc"
  moved=1
fi

stow --dir="$repo_dir" --no-folding --simulate --verbose --target="$target_home" bash
stow --dir="$repo_dir" --no-folding --target="$target_home" bash

moved=0
trap - 0
printf '%s\n' 'Bash configuration installed; start a new interactive bash to use it.'

#!/bin/sh
# Install the optional local resolver runtime; prompt rendering stays offline.
set -eu
command -v uv >/dev/null 2>&1 || { printf 'uv is required\n' >&2; exit 1; }
runtime="${HOME}/.local/share/terminal-dotfiles/kube-env-venv"
uv venv --python '>=3.10' "$runtime"
uv pip install --python "$runtime/bin/python" 'PyYAML==6.0.3'
printf 'Kubernetes environment runtime ready\n'

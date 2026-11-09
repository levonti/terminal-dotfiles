from pathlib import Path
import shutil
import sys
import shlex

ROOT = Path(__file__).resolve().parents[1]


def install(home):
    home = Path(home)
    target = home / '.config/terminal-dotfiles'
    target.mkdir(parents=True, exist_ok=True)
    for name in ('kube-environment', 'kube_environment.py'):
        shutil.copy(ROOT / 'zsh/.config/terminal-dotfiles' / name, target / name)
    runtime = home / '.local/share/terminal-dotfiles/kube-env-venv/bin'
    runtime.mkdir(parents=True)
    (runtime / 'python').write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' "$@"\n')
    (runtime / 'python').chmod(0o755)

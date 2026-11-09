from kube_fixture import install
"""Exercise real local programs in a PTY, with isolated state and no cluster API."""

import base64
import fcntl
import os
from pathlib import Path
import pty
import re
import select
import shlex
import shutil
import signal
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory
import termios
from time import monotonic
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "kitty/.config/kitty"))
import tab_bar

TOOLS = {name: shutil.which(name) for name in ("zsh", "kubie", "starship", "htop", "ps")}


@unittest.skipUnless(all(TOOLS.values()), "Real cycle requires zsh, kubie, starship, htop and ps")
class RealKubieCycleTests(unittest.TestCase):
    def test_context_htop_exit_namespace_and_reentry(self):
        with TemporaryDirectory(prefix="kitty-kubie-cycle-") as directory:
            fixture = Path(directory)
            install(fixture)
            (fixture / ".kube").mkdir()
            (fixture / "project").mkdir()
            (fixture / "bin").mkdir()
            api_guard = fixture / "api-attempted"
            kubectl = fixture / "bin/kubectl"
            kubectl.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(api_guard))}\nexit 99\n")
            kubectl.chmod(0o755)
            (fixture / ".kube/kubie.yaml").write_text(
                f"shell: zsh\nprompt:\n  disable: true\nbehavior:\n  validate_namespaces: false\n"
                f"configs:\n  include:\n    - {fixture / '.kube/configs/lab/prod/config.yaml'}\n")
            source = fixture / ".kube/configs/lab/prod/config.yaml"
            source.parent.mkdir(parents=True)
            source.write_text(
                "apiVersion: v1\nkind: Config\ncurrent-context: prod:fixture\ncontexts:\n"
                "- name: prod:fixture\n  context:\n    cluster: fixture\n    user: fixture\n    namespace: app\n"
                "clusters:\n- name: fixture\n  cluster:\n    server: https://example.invalid\n"
                "users:\n- name: fixture\n  user: {}\n")
            # Ignore insecure completion directories without prompting in the PTY.
            (fixture / ".zshrc").write_text(
                "alias compinit='compinit -i'\n"
                f"source {shlex.quote(str(ROOT / 'zsh/.zshrc'))}\n"
                "unalias compinit\n"
                "function _fixture_ready() {\n"
                "  if [[ $PS1 != *fixture-ready* ]]; then PS1+=$'%{\\e]777;fixture-ready;'\"$$\"$'\\a%}'; fi\n"
                "  return 0\n}\n"
                "add-zsh-hook precmd _fixture_ready\n")
            path = list(dict.fromkeys([str(fixture / "bin"), *(str(Path(p).parent) for p in TOOLS.values()),
                                      *os.defpath.split(os.pathsep), "/usr/sbin", "/sbin"]))
            # HOME is scoped to the spawned test process only. Kubie's settings,
            # namespace history, shell rc files and htop settings stay disposable.
            # Kubie sources Ubuntu's global zshrc again in the nested shell.
            env = dict(HOME=str(fixture), PATH=os.pathsep.join(path), SHELL=TOOLS["zsh"],
                       TERM="xterm-256color", LANG="en_US.UTF-8", KITTY_WINDOW_ID="42", KITTY_PID="1",
                       STARSHIP_CONFIG=str(ROOT / "starship/.config/starship.toml"),
                       HTOPRC=str(fixture / "htoprc"), skip_global_compinit="1")
            integration = Path("/Applications/kitty.app/Contents/Resources/kitty/shell-integration/zsh")
            if (integration / ".zshenv").exists():
                # Match Kitty's initial launch. Kubie then starts its own shell
                # without re-injecting this native integration, as in real use.
                env.update(KITTY_SHELL_INTEGRATION="enabled", ZDOTDIR=str(integration))
            pid, fd = pty.fork()
            if pid == 0:
                os.chdir(fixture / "project")
                os.execve(TOOLS["zsh"], ["zsh", "-i"], env)
            fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 140, 0, 0))
            variables = {}
            at_prompt = True
            native_title = "~"

            def wait_for(kind):
                nonlocal at_prompt, native_title
                output = b""
                deadline = monotonic() + 10
                while monotonic() < deadline:
                    if select.select([fd], [], [], 0.1)[0]:
                        output += os.read(fd, 65536)
                        ready = re.search(rb"\x1b\]777;fixture-ready;[0-9]+\x07", output)
                        alternate = re.search(rb"\x1b\[\?(1049|1047|47)h", output)
                        if (kind == "prompt" and ready) or (kind == "tui" and alternate):
                            for key, value in re.findall(rb"\x1b\]1337;SetUserVar=([^=;]+)=([^\x07]*)\x07", output):
                                variables[key.decode()] = base64.b64decode(value).decode()
                            marks = re.findall(rb"\x1b\]133;([AC])", output)
                            if marks:
                                at_prompt = marks[-1] == b"A"
                            titles = re.findall(rb"\x1b\][02];([^\x07]*)\x07", output)
                            if titles:
                                native_title = titles[-1].decode()
                            return output.decode(errors="replace")
                self.fail(f"No {kind} state in the isolated Kubie PTY. Output tail: {output[-1500:]!r}")

            def render(expected, prompt_output=None, htop=False, prompt_label=None):
                group = os.tcgetpgrp(fd)
                rows = subprocess.check_output([TOOLS["ps"], "-axo", "pid=,pgid=,comm="], text=True)
                foreground = []
                for row in rows.splitlines():
                    fields = row.strip().split(None, 2)
                    if len(fields) == 3 and fields[1] == str(group):
                        foreground.append((int(fields[0]), Path(fields[2]).name.strip("()")))
                foreground_pid, executable = max(foreground) if foreground else (pid, "zsh")
                if htop:
                    self.assertIn("htop", [item[1] for item in foreground])
                window = SimpleNamespace(id=9001, user_vars=dict(variables), child_is_remote=False,
                    child=SimpleNamespace(pid=pid, pid_for_cwd=foreground_pid, foreground_cmdline=[executable], foreground_environ={}),
                    at_prompt=at_prompt, get_cwd_of_child=lambda: str(fixture / "project"))
                tab = SimpleNamespace(name="", active_window=window)
                fast = ModuleType("kitty.fast_data_types")
                fast.get_boss = lambda: SimpleNamespace(tab_for_id=lambda _: tab)
                with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast}):
                    actual = tab_bar.draw_title({"tab_id": 1, "title": native_title})
                self.assertEqual(actual, expected)
                self.assertNotIn("·", actual)
                self.assertNotIn("kubie", actual)
                if prompt_label is not None:
                    self.assertIn(prompt_label, tab_bar.plain_title(prompt_output))
                self.assertFalse(api_guard.exists(), "The isolated cycle attempted kubectl/API access")

            try:
                render("project", wait_for("prompt"))
                # One fixture context is selected automatically by real `kubie ctx`.
                os.write(fd, b"kubie ctx -n app\n")
                render("PROD prod:fixture::app project", wait_for("prompt"), prompt_label="[PROD prod:fixture::app]")
                for iteration in range(2):
                    os.write(fd, b"htop --readonly --pid $$\n")
                    wait_for("tui")
                    render("PROD prod:fixture::app project htop", htop=True)
                    os.write(fd, b"q")
                    render("PROD prod:fixture::app project", wait_for("prompt"), prompt_label="[PROD prod:fixture::app]")
                    os.write(fd, b"kubie ns changed\n")
                    render("PROD prod:fixture::changed project", wait_for("prompt"), prompt_label="[PROD prod:fixture::changed]")
                    os.write(fd, b"exit\n")
                    render("project", wait_for("prompt"))
                    if iteration == 0:
                        os.write(fd, b"kubie ctx prod:fixture -n app\n")
                        render("PROD prod:fixture::app project", wait_for("prompt"), prompt_label="[PROD prod:fixture::app]")
            finally:
                os.close(fd)
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                os.waitpid(pid, 0)


if __name__ == "__main__":
    unittest.main()

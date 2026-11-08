import base64
import os
from pathlib import Path
import pty
import re
import select
import signal
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
BASH_SHELLS = list(dict.fromkeys(str(Path(p).resolve()) for p in (shutil.which("bash"), "/bin/bash") if p and Path(p).exists()))
SHELLS = BASH_SHELLS + (["zsh"] if shutil.which("zsh") else [])
sys.path.insert(0, str(ROOT / "kitty/.config/kitty"))
import tab_bar as tabs


def hook_block(shell):
    source = (ROOT / ("zsh/.zshrc" if shell == "zsh" else "bash/.bashrc")).read_text()
    block = source[source.index("# Publish the same Kubernetes"):]
    return block[:block.index("# Use compatible terminfo")] if shell == "zsh" else block


class TitleTests(unittest.TestCase):
    def setUp(self):
        tabs._remote_locations.clear()

    def test_paths_commands_and_remote_identity(self):
        cases = {
            "~": "~", "~/": "~", "/": "/", "~/work/project/": "project",
            "/srv/My Project": "My Project", "…/work/проект": "проект",
            "user@host: ~/work/project": "host:project",
            "host: ~": "host:~", "root@host: /srv/project": "root@host:project",
            "host: tmux new -s work": "host:tmux", "btop": "btop",
            "k8s: dev:example/app": "k8s:dev:example/app",
            "": "shell", "hi\x1b\nthere": "hithere",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(tabs.compact_title(source), expected)

    def render(self, title, name="", context="", active=True, remote=False,
               cwd="/work/project", at_prompt=True, argv=None, owner=None, kubie=True, reported=""):
        value = f"{os.getpid() if owner is None else owner}|{context}" if context else ""
        window = SimpleNamespace(id=1, user_vars={"terminal_dotfiles_kubie": value},
            child_is_remote=remote, get_cwd_of_child=lambda: cwd, at_prompt=at_prompt,
            child=SimpleNamespace(foreground_environ={"KUBIE_ACTIVE": "1"} if kubie else {},
                                  foreground_cmdline=argv or ["zsh"]),
            screen=SimpleNamespace(last_reported_cwd=reported), last_cmd_cmdline=title)
        tab = SimpleNamespace(name=name, active_window=window)
        module = ModuleType("kitty.fast_data_types")
        module.get_boss = lambda: SimpleNamespace(tab_for_id=lambda _: tab)
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": module}):
            return tabs.draw_title({"title": title, "tab_id": 1, "is_active": active})

    def test_focus_preserves_label(self):
        for title in ("user@host: ~/project", "root@host: ~", "~", "~/project"):
            self.assertEqual(self.render(title, active=True), self.render(title, active=False))

    def test_explicit_names_are_verbatim_and_override_context(self):
        self.assertEqual(self.render("kubie ctx", name="Deploy: production console",
                                     context="[☸ DEV example::default]"), "Deploy: production console")

    def test_context_survives_running_commands_and_clears_after_exit(self):
        self.assertEqual(self.render("htop", context="[☸ DEV example::app]", at_prompt=False, argv=["htop"]),
                         "[☸ DEV example::app] project · htop")
        # Simulate returning to a parent which never loaded the new hooks.
        self.assertEqual(self.render("~", context="[☸ DEV example::app]", kubie=False), "project")

    def test_exited_metadata_owner_is_rejected_even_in_another_kubie_shell(self):
        with patch.object(tabs.os, "kill", side_effect=ProcessLookupError):
            self.assertEqual(self.render("~", context="[☸ PROD example::app]"), "project")

    def test_unscoped_legacy_metadata_is_rejected(self):
        window = SimpleNamespace(child_is_remote=False, child=SimpleNamespace(foreground_environ={"KUBIE_ACTIVE": "1"}),
                                 user_vars={"terminal_dotfiles_kubie": "k8s: dev:example/app"})
        self.assertEqual(tabs.kubie_label(window), "")

    def test_local_commands_keep_directory_without_exposing_arguments(self):
        self.assertEqual(self.render("htop --sort PERCENT_CPU", at_prompt=False, argv=["/bin/htop"]), "project · htop")
        self.assertEqual(self.render("curl secret-argument", at_prompt=False, argv=["curl", "secret-argument"]), "project · curl")
        self.assertEqual(self.render("~", cwd=str(Path.home())), "~")

    def test_preexec_title_before_command_start_marker_already_shows_command(self):
        self.assertEqual(self.render("htop", at_prompt=True, argv=["zsh"]), "project · htop")

    def test_return_to_parent_invalidates_same_frame_cache(self):
        child = SimpleNamespace(pid_for_cwd=101, foreground_cmdline=["zsh"], foreground_environ={"KUBIE_ACTIVE": "1"})
        window = SimpleNamespace(id=1, child=child, child_is_remote=False, at_prompt=True,
            user_vars={"terminal_dotfiles_kubie": f"{os.getpid()}|[☸ DEV example::app]"},
            get_cwd_of_child=lambda: "/work/project")
        tab = SimpleNamespace(name="", active_window=window)
        fast = ModuleType("kitty.fast_data_types")
        fast.get_boss = lambda: SimpleNamespace(tab_for_id=lambda _: tab)
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast}), patch.object(tabs, "monotonic", return_value=10):
            self.assertEqual(tabs.draw_title({"tab_id": 1, "title": "~"}), "[☸ DEV example::app] project")
            child.pid_for_cwd, child.foreground_environ = 100, {}
            self.assertEqual(tabs.draw_title({"tab_id": 1, "title": "~"}), "project")

    def test_remote_commands_keep_last_remote_directory_and_ignore_local_kubie(self):
        self.assertEqual(self.render("user@host: /srv/project", remote=True), "host:project")
        self.assertEqual(self.render("user@host: htop -d 5", remote=True, context="[☸ DEV local::app]"), "host:project · htop")
        self.assertEqual(self.render("htop", remote=True), "host:project · htop")
        self.assertEqual(self.render("user@host: /srv/project", remote=True), "host:project")

    def test_remote_reported_path_and_change_of_host(self):
        self.assertEqual(self.render("root@host: htop", remote=True, reported="file://host/srv/project"), "root@host:project · htop")
        self.assertEqual(self.render("user@other: htop", remote=True), "other · htop")

    def test_remote_combined_title(self):
        self.assertEqual(self.render("user@host: /srv/project · htop", remote=True), "host:project · htop")

    def test_new_local_session_discards_remote_location(self):
        self.render("user@host: /srv/old", remote=True)
        self.render("~", kubie=False)
        self.assertEqual(self.render("user@host: htop", remote=True), "host · htop")

    def test_long_titles_keep_the_running_command_visible(self):
        fast = ModuleType("kitty.fast_data_types")
        fast.wcswidth = len
        api = ModuleType("kitty.tab_bar")
        api.truncate_line = lambda text, width: text[:max(0, width - 1)] + "…"
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": fast, "kitty.tab_bar": api}):
            for width in (12, 20, 28, 40):
                result = tabs.fit_title(" 1 host:very-long-project-name-for-testing · htop", width)
                self.assertLessEqual(len(result), width)
                self.assertTrue(result.startswith(" 1 "))
                self.assertTrue(result.endswith(" · htop"))


class LayoutTests(unittest.TestCase):
    snapshot = ([(59, 1_000_000, 250_000), (60, 0, 0)], 1_000_000, 250_000, "ready")

    def test_tabs_take_priority_at_eight_tabs_in_requested_sizes(self):
        desired = [14, 16, 12, 20, 18, 10, 24, 23]
        for columns in (80, 120, 160):
            for platform in ("darwin", "linux"):
                with self.subTest(columns=columns, platform=platform):
                    _, panel = tabs.format_panel(self.snapshot, max(0, columns - sum(desired) - 1), 60, platform)
                    widths = tabs.allocate_widths(desired, columns - panel - 1)
                    self.assertTrue(all(w >= 8 for w in widths))
                    self.assertLessEqual(sum(widths) + panel + 1, columns)
                    self.assertEqual(widths, tabs.allocate_widths(desired, columns - 1))

    def test_panel_uses_only_spare_space_and_shrinks_in_three_stages(self):
        for platform, expected in (("darwin", (0, 25, 43)), ("linux", (0, 27, 45))):
            widths = [tabs.format_panel(self.snapshot, budget, 60, platform)[1] for budget in (20, 30, 50)]
            self.assertEqual(tuple(widths), expected)

    def test_old_119_120_boundary_has_no_effect(self):
        desired = [12] * 8
        for columns in (119, 120):
            _, panel = tabs.format_panel(self.snapshot, columns - sum(desired) - 1, 60, "darwin")
            self.assertEqual(panel, 0)
            self.assertEqual(tabs.allocate_widths(desired, columns - 1), desired)

    def test_root_priority_does_not_starve_other_tabs(self):
        widths = tabs.allocate_widths([28] * 8, 100, (2,))
        self.assertEqual(widths[2], 28)
        self.assertTrue(all(w >= 8 for w in widths))
        self.assertEqual(sum(widths), 100)


class ShellMetadataTests(unittest.TestCase):
    def run_hook(self, shell, active="1", failing=False, array=False, context=None):
        # Exercise the complete registration block without loading private rc files.
        block = hook_block(shell)
        with TemporaryDirectory() as directory:
            binary = Path(directory) / "starship"
            binary.write_text("#!/bin/sh\n" + ("exit 1\n" if failing else
                              'case "$*" in "module kubernetes") printf "\\033[32m[☸ DEV example::app]\\033[0m ";; *) exit 90;; esac\n'))
            if context is not None:
                binary.write_text(f'#!/bin/sh\nexec {shutil.which("starship")} "$@"\n')
            binary.chmod(0o755)
            config = Path(directory) / "kubeconfig"
            config.write_text(f'apiVersion: v1\nkind: Config\ncurrent-context: {context or "dev:example"}\n'
                              f'contexts:\n- name: {context or "dev:example"}\n  context:\n    cluster: example\n'
                              '    user: example\n    namespace: app\nclusters:\n- name: example\n'
                              '  cluster:\n    server: https://example.invalid\nusers:\n- name: example\n  user: {}\n')
            env = {**os.environ, "KITTY_WINDOW_ID": "42", "KUBIE_ACTIVE": active,
                   "PATH": f"{directory}:/usr/bin:/bin", "SSH_TTY": "", "SSH_CONNECTION": "", "TERM": "dumb",
                   "STARSHIP_CONFIG": str(ROOT / "starship/.config/starship.toml"), "KUBECONFIG": str(config)}
            prefix = 'PROMPT_COMMAND=("printf preserved")\n' if array else 'PROMPT_COMMAND="printf preserved"\n'
            script = prefix + block + "\n" + block + "\n_terminal_dotfiles_kubie_title\n"
            if shell == "zsh":
                script += 'print -r -- "${precmd_functions[*]}"\n'
            else:
                script += 'printf "%s\\n" "${PROMPT_COMMAND[*]}"\n'
            result = subprocess.run([shell, "-fc" if shell == "zsh" else "--noprofile", *(
                [] if shell == "zsh" else ["--norc", "-c"]), script],
                env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout

    def test_both_shells_publish_context_and_register_once(self):
        for shell in SHELLS:
            output = self.run_hook(shell)
            value = re.search(r"SetUserVar=terminal_dotfiles_kubie=([^\a]+)\a", output)[1]
            owner, label = base64.b64decode(value).decode().split("|", 1)
            self.assertTrue(owner.isdecimal())
            self.assertEqual(label, "[☸ DEV example::app] ")
            self.assertEqual(output.count("_terminal_dotfiles_kubie_title"), 1)

    @unittest.skipUnless(shutil.which("starship"), "Starship is not installed")
    def test_actual_prompt_module_format_for_all_environment_aliases(self):
        for context, label in (("dev:example", "DEV example"), ("test:example", "TEST example"),
                               ("prod:example", "! PROD example"), ("other/cluster", "? ENV cluster"),
                               ("dev/region/example", "DEV example")):
            for shell in SHELLS:
                output = self.run_hook(shell, context=context)
                value = re.search(r"SetUserVar=terminal_dotfiles_kubie=([^\a]+)\a", output)[1]
                self.assertEqual(base64.b64decode(value).decode().split("|", 1)[1].strip(), f"[☸ {label}::app]")

    def test_outer_shell_and_failed_reads_clear_stale_context(self):
        for shell in SHELLS:
            for options in ({"active": ""}, {"failing": True}):
                self.assertIn("SetUserVar=terminal_dotfiles_kubie=\a", self.run_hook(shell, **options))

    def test_bash_preserves_scalar_and_array_prompt_commands(self):
        for shell in BASH_SHELLS:
            for array in (False, True):
                self.assertIn("printf preserved", self.run_hook(shell, array=array))


class RemotePtyTests(unittest.TestCase):
    def test_real_interactive_remote_hooks_report_command_then_restore_directory(self):
        # A real PTY and interactive shells, with no server or Kitty GUI involved.
        for shell in SHELLS:
            with self.subTest(shell=shell), TemporaryDirectory() as directory:
                rc = Path(directory) / "rc"
                rc.write_text(hook_block(shell) + '\nPS1="__TABS_READY__ "\n')
                pid, fd = pty.fork()
                if pid == 0:
                    env = {**os.environ, "KITTY_WINDOW_ID": "", "KUBIE_ACTIVE": "", "TERM": "xterm-256color",
                           "SSH_TTY": "/dev/pts/test", "SSH_CONNECTION": "test", "HISTFILE": "/dev/null",
                           "HISTCONTROL": "", "HISTIGNORE": ""}
                    args = [shell, "-f"] if shell == "zsh" else [shell, "--noprofile", "--rcfile", str(rc), "-i"]
                    os.execvpe(shell, args, env)
                def read_until_ready():
                    output = b""
                    deadline = monotonic() + 5
                    while monotonic() < deadline:
                        if select.select([fd], [], [], 0.1)[0]:
                            output += os.read(fd, 65536)
                            plain = re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", output)
                            if plain.rstrip().endswith(b"__TABS_READY__"):
                                return output.decode(errors="replace")
                    self.fail(f"No interactive prompt from {shell}: {output[-200:]!r}")
                try:
                    if shell == "zsh":
                        os.write(fd, f'source {rc}\n'.encode())
                    first = read_until_ready()
                    os.write(fd, b"sleep 0.1\n")
                    output = read_until_ready()
                    titles = re.findall(r"\x1b\]2;([^\a]+)\a", output)
                    self.assertTrue(titles)
                    self.assertNotIn(" · ", titles[-1])
                    # PS0 is available starting with Bash 4.4; zsh has preexec.
                    modern = shell == "zsh" or int(subprocess.check_output([shell, "-c", 'printf "%s" "$BASH_VERSINFO"'])) >= 5
                    if modern:
                        self.assertTrue(any(t.endswith(" · sleep") for t in titles), titles)
                    self.assertTrue(re.findall(r"\x1b\]2;([^\a]+)\a", first))
                finally:
                    os.close(fd)
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.waitpid(pid, 0)


class MetadataLifecycleTests(unittest.TestCase):
    def test_real_shell_exit_invalidates_metadata_without_parent_refresh(self):
        for shell in SHELLS:
            with self.subTest(shell=shell), TemporaryDirectory() as directory:
                starship = Path(directory) / "starship"
                starship.write_text("#!/bin/sh\nprintf '[☸ DEV example::app]'\n")
                starship.chmod(0o755)
                script = hook_block(shell) + "\n_terminal_dotfiles_kubie_title\nbuiltin read -r line\n"
                env = {**os.environ, "KITTY_WINDOW_ID": "42", "KUBIE_ACTIVE": "1",
                       "SSH_TTY": "", "SSH_CONNECTION": "", "PATH": f"{directory}:/usr/bin:/bin"}
                args = [shell, "-fc", script] if shell == "zsh" else [shell, "--noprofile", "--norc", "-c", script]
                proc = subprocess.Popen(args, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    output = b""
                    deadline = monotonic() + 3
                    while b"\a" not in output and monotonic() < deadline:
                        if select.select([proc.stdout], [], [], 0.1)[0]:
                            output += os.read(proc.stdout.fileno(), 4096)
                    value = re.search(rb"SetUserVar=terminal_dotfiles_kubie=([^\a]+)\a", output)
                    self.assertIsNotNone(value)
                    decoded = base64.b64decode(value[1]).decode()
                    window = SimpleNamespace(child_is_remote=False,
                        child=SimpleNamespace(foreground_environ={"KUBIE_ACTIVE": "1"}),
                        user_vars={"terminal_dotfiles_kubie": decoded})
                    self.assertEqual(tabs.kubie_label(window), "[☸ DEV example::app]")
                    proc.stdin.close()
                    proc.wait(timeout=3)
                    # The parent never sends a clear; the exited PID is enough.
                    self.assertEqual(tabs.kubie_label(window), "")
                finally:
                    if proc.poll() is None:
                        proc.kill()
                        proc.wait()
                    for stream in (proc.stdin, proc.stdout, proc.stderr):
                        stream.close()


if __name__ == "__main__":
    unittest.main()

import base64
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
BASH_SHELLS = list(dict.fromkeys(str(Path(p).resolve()) for p in (shutil.which("bash"), "/bin/bash") if p and Path(p).exists()))
SHELLS = BASH_SHELLS + (["zsh"] if shutil.which("zsh") else [])
sys.path.insert(0, str(ROOT / "kitty/.config/kitty"))
import tab_bar as tabs


class TitleTests(unittest.TestCase):
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

    def render(self, title, name="", context="", active=True):
        tab = SimpleNamespace(name=name, active_window=SimpleNamespace(
            user_vars={"terminal_dotfiles_kubie": context}))
        module = ModuleType("kitty.fast_data_types")
        module.get_boss = lambda: SimpleNamespace(tab_for_id=lambda _: tab)
        with patch.dict(sys.modules, {"kitty": ModuleType("kitty"), "kitty.fast_data_types": module}):
            return tabs.draw_title({"title": title, "tab_id": 1, "is_active": active})

    def test_focus_preserves_label(self):
        for title in ("user@host: ~/project", "root@host: ~", "~", "~/project"):
            self.assertEqual(self.render(title, active=True), self.render(title, active=False))

    def test_explicit_names_are_verbatim_and_override_context(self):
        self.assertEqual(self.render("kubie ctx", name="Deploy: production console",
                                     context="k8s:dev:example/default"), "Deploy: production console")

    def test_context_survives_running_commands_and_clears_after_exit(self):
        self.assertEqual(self.render("kubie ctx", context="k8s: dev:example/app"), "k8s:dev:example/app")
        self.assertEqual(self.render("~", context=""), "~")


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
    def run_hook(self, shell, active="1", failing=False, array=False):
        file = ROOT / ("zsh/.zshrc" if shell == "zsh" else "bash/.bashrc")
        source = file.read_text()
        # Exercise the complete registration block without loading private rc files.
        marker = "# Publish only" if shell == "zsh" else "# Publish local"
        block = source[source.index(marker):]
        if shell == "zsh":
            block = block[:block.index("# Use compatible terminfo")]
        with TemporaryDirectory() as directory:
            binary = Path(directory) / "kubie"
            binary.write_text("#!/bin/sh\n" + ("exit 1\n" if failing else
                              'case "$*" in "info ctx") printf "dev:example\\n";; '
                              '"info ns") printf "app\\n";; *) exit 90;; esac\n'))
            binary.chmod(0o755)
            env = {**os.environ, "KITTY_WINDOW_ID": "42", "KUBIE_ACTIVE": active,
                   "PATH": f"{directory}:/usr/bin:/bin"}
            prefix = 'PROMPT_COMMAND=("printf preserved")\n' if array else 'PROMPT_COMMAND="printf preserved"\n'
            script = prefix + block + "\n" + block + "\n_terminal_dotfiles_kubie_title\n"
            if shell == "zsh":
                script += 'print -r -- "${precmd_functions[*]}"\n'
            else:
                script += 'printf "%s\\n" "${PROMPT_COMMAND[*]}"\n'
            result = subprocess.run([shell, "-fc" if shell == "zsh" else "--noprofile", *(
                [] if shell == "zsh" else ["--norc", "-c"]), script],
                env=env, capture_output=True, text=True, check=True)
            return result.stdout

    def test_both_shells_publish_context_and_register_once(self):
        expected = base64.b64encode(b"k8s: dev:example/app").decode()
        for shell in SHELLS:
            output = self.run_hook(shell)
            self.assertIn(f"SetUserVar=terminal_dotfiles_kubie={expected}\a", output)
            self.assertEqual(output.count("_terminal_dotfiles_kubie_title"), 1)

    def test_outer_shell_and_failed_reads_clear_stale_context(self):
        for shell in SHELLS:
            for options in ({"active": ""}, {"failing": True}):
                self.assertIn("SetUserVar=terminal_dotfiles_kubie=\a", self.run_hook(shell, **options))

    def test_bash_preserves_scalar_and_array_prompt_commands(self):
        for shell in BASH_SHELLS:
            for array in (False, True):
                self.assertIn("printf preserved", self.run_hook(shell, array=array))


if __name__ == "__main__":
    unittest.main()

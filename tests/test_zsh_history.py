import os
from pathlib import Path
import select
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")


@unittest.skipUnless(ZSH, "Zsh is required to exercise interactive history")
class ZshHistoryTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix="terminal-dotfiles-history-")
        self.addCleanup(directory.cleanup)
        self.home = Path(directory.name)
        (self.home / ".zshrc").symlink_to(ROOT / "zsh/.zshrc")
        self.env = dict(HOME=str(self.home), ZDOTDIR=str(self.home), PATH=os.defpath, TERM="dumb")

    def start_shell(self):
        return subprocess.Popen(
            [ZSH, "-di"], cwd=self.home, env=self.env, text=True,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

    def run_command(self, shell, command):
        shell.stdin.write(command + "\n")
        shell.stdin.flush()
        self.assertTrue(select.select([shell.stdout], [], [], 10)[0], "No output from Zsh")
        return shell.stdout.readline().strip()

    def test_history_is_shared_before_exit_and_restored_on_startup(self):
        history = self.home / ".zsh_history"
        history.write_text("print -r -- previous-history\n")

        with self.start_shell() as reader:
            self.assertEqual(self.run_command(reader, "print -r -- reader-ready"), "reader-ready")
            with self.start_shell() as writer:
                command = "print -r -- shared-command"
                self.assertEqual(self.run_command(writer, command), "shared-command")
                self.assertIn(command, history.read_text())

                stdout, stderr = reader.communicate("fc -l 1\nexit\n", timeout=10)
                self.assertEqual(reader.returncode, 0, stderr)
                self.assertIn(command, stdout)

                writer.kill()
                writer.wait(timeout=10)

        with self.start_shell() as reopened:
            stdout, stderr = reopened.communicate("fc -l 1\nexit\n", timeout=10)
            self.assertEqual(reopened.returncode, 0, stderr)
            self.assertIn("print -r -- previous-history", stdout)
            self.assertIn(command, stdout)

    def test_local_history_settings_override_defaults(self):
        (self.home / ".zshrc.local").write_text('HISTFILE="$HOME/custom-history"\nHISTSIZE=600\n')
        (self.home / ".zshrc.local.post").write_text("SAVEHIST=500\nsetopt INC_APPEND_HISTORY\n")

        with self.start_shell() as shell:
            stdout, stderr = shell.communicate(
                'print -r -- "$HISTFILE|$HISTSIZE|$SAVEHIST|${options[sharehistory]}|${options[incappendhistory]}"\n'
                'exit\n',
                timeout=10,
            )
            self.assertEqual(shell.returncode, 0, stderr)
            self.assertEqual(stdout.strip(), f"{self.home / 'custom-history'}|600|500|off|on")
        self.assertTrue((self.home / "custom-history").is_file())
        self.assertFalse((self.home / ".zsh_history").exists())

import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT = Path(__file__).resolve().parents[1]
STARSHIP = shutil.which('starship')
GIT = shutil.which('git')


@unittest.skipUnless(STARSHIP and GIT, 'Starship prompt test requires starship and git')
class StarshipPromptTests(unittest.TestCase):
    def test_git_branch_shortening_and_conditional_separators(self):
        with TemporaryDirectory(prefix='starship-git-prompt-') as directory:
            home = Path(directory).resolve()
            repo = home / 'project'
            repo.mkdir()
            helper = home / '.config/terminal-dotfiles/kube-environment'
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/bin/sh\nprintf '[PROD] LAB core01 / app'\n")
            helper.chmod(0o755)
            env = dict(HOME=str(home), PATH=os.environ['PATH'], TERM='xterm-256color',
                       LANG='en_US.UTF-8', STARSHIP_SHELL='zsh', GIT_CONFIG_NOSYSTEM='1',
                       STARSHIP_CONFIG=str(ROOT / 'starship/.config/starship.toml'))

            def git(*args):
                subprocess.run([GIT, *args], cwd=repo, env=env, check=True, capture_output=True)

            def prompt(path, *, kube=False):
                active_env = dict(env, KUBIE_ACTIVE='1') if kube else env
                result = subprocess.run([STARSHIP, 'prompt'], cwd=path, env=active_env,
                                        check=True, capture_output=True, text=True)
                return re.sub(r'\x1b\[[0-9;:]*m|%[{}]', '', result.stdout).strip()

            self.assertEqual(prompt(home), 'zsh  ~ \n❯')
            self.assertEqual(prompt(home, kube=True), 'zsh 󱃾 [PROD] LAB core01 / app │  ~ \n❯')

            branch = 'ai/kitty-active-tab-background'
            git('init', '-qb', 'main')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                'commit', '--allow-empty', '-qm', 'fixture')
            git('switch', '-qc', branch)
            self.assertEqual(prompt(repo), 'zsh  project │  ai/…tab-background \n❯')
            self.assertEqual(prompt(repo, kube=True),
                             'zsh 󱃾 [PROD] LAB core01 / app │  project │  ai/…tab-background \n❯')

            helper.write_text('#!/bin/sh\nexit 0\n')
            self.assertEqual(prompt(repo, kube=True), prompt(repo))

            git('remote', 'add', 'origin', str(home / 'unused-remote'))
            git('update-ref', 'refs/remotes/origin/trunk', 'HEAD')
            git('branch', '--set-upstream-to=origin/trunk')
            (repo / 'untracked').touch()
            self.assertIn('│  ai/…tab-background:trunk ?1', prompt(repo))

            git('switch', '-q', 'main')
            self.assertIn('│  main ?1', prompt(repo))
            git('switch', '-q', '--detach')
            self.assertIn('│  HEAD ?1', prompt(repo))

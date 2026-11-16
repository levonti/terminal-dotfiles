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
BASH = shutil.which('bash')


@unittest.skipUnless(STARSHIP and GIT, 'Starship prompt test requires starship and git')
class StarshipPromptTests(unittest.TestCase):
    def test_git_branch_shortening_and_conditional_separators(self):
        with TemporaryDirectory(prefix='starship-git-prompt-') as directory:
            home = Path(directory).resolve()
            repo = home / 'project'
            repo.mkdir()
            env = dict(HOME=str(home), PATH=os.environ['PATH'], TERM='xterm-256color',
                       LANG='en_US.UTF-8', STARSHIP_SHELL='zsh', GIT_CONFIG_NOSYSTEM='1',
                       STARSHIP_CONFIG=str(ROOT / 'starship/.config/starship.toml'))

            def git(*args):
                subprocess.run([GIT, *args], cwd=repo, env=env, check=True, capture_output=True)

            def prompt(path, *, kube=False):
                active_env = env.copy()
                if kube:
                    active_env['TERMINAL_DOTFILES_KUBE_PROMPT'] = '[PROD] LAB core01 / app'
                if path == home:
                    active_env['STARSHIP_LOG'] = 'trace'
                result = subprocess.run([STARSHIP, 'prompt'], cwd=path, env=active_env,
                                        check=True, capture_output=True, text=True)
                if path == home:
                    self.assertNotIn('Building HashSets of directory', result.stderr)
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

            git('remote', 'add', 'origin', str(home / 'unused-remote'))
            git('update-ref', 'refs/remotes/origin/trunk', 'HEAD')
            git('branch', '--set-upstream-to=origin/trunk')
            (repo / 'untracked').touch()
            self.assertIn('│  ai/…tab-background:trunk ?1', prompt(repo))

            git('switch', '-q', 'main')
            self.assertIn('│  main ?1', prompt(repo))
            git('switch', '-q', '--detach')
            self.assertIn('│  HEAD ?1', prompt(repo))

    @unittest.skipUnless(BASH, 'Interactive Bash is required')
    def test_bash_refreshes_kubie_prompt_and_preserves_user_hook(self):
        with TemporaryDirectory(prefix='starship-bash-prompt-') as directory:
            home = Path(directory).resolve()
            helper = home / '.config/terminal-dotfiles/kube-environment'
            helper.parent.mkdir(parents=True)
            helper.write_text("#!/bin/sh\nprintf '%s' 'fixture-kubie-context'\n")
            helper.chmod(0o755)
            (home / '.bashrc.local').write_text('user_hook() { ((hook_count += 1)); }\n'
                                                'starship_precmd_user_func=user_hook\n')
            env = dict(HOME=str(home), PATH=os.environ['PATH'], TERM='xterm-256color',
                       LANG='en_US.UTF-8', STARSHIP_CONFIG=str(ROOT / 'starship/.config/starship.toml'))
            result = subprocess.run([BASH, '--noprofile', '--rcfile', str(ROOT / 'bash/.bashrc'), '-ic', '''
export KUBIE_ACTIVE=1
starship_precmd
[[ $PS1 == *fixture-kubie-context* ]] || exit 1
unset KUBIE_ACTIVE
starship_precmd
[[ $PS1 != *fixture-kubie-context* && $hook_count == 2 ]]
'''], cwd=home, env=env, timeout=10, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

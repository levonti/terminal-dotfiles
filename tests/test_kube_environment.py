import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import yaml

spec = importlib.util.spec_from_file_location('resolver', Path(__file__).resolve().parents[1] / 'zsh/.config/terminal-dotfiles/kube_environment.py')
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)


class ResolutionTests(unittest.TestCase):
    def test_oidc_refresh_keeps_the_environment(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            source = home / '.kube/configs/lab/dev/fixture.yaml'
            source.parent.mkdir(parents=True)
            (home / '.kube/kubie.yaml').write_text('configs:\n  include: ["~/.kube/configs/**/*.yaml"]\n')
            provider = {'name': 'oidc', 'config': {
                'idp-issuer-url': 'https://issuer.example.invalid', 'client-id': 'fixture',
                'id-token': 'old-id', 'refresh-token': 'old-refresh',
            }}
            doc = {
                'current-context': 'demo',
                'contexts': [{'name': 'demo', 'context': {'cluster': 'c', 'user': 'u'}}],
                'clusters': [{'name': 'c', 'cluster': {'server': 'https://example.invalid'}}],
                'users': [{'name': 'u', 'user': {'auth-provider': provider}}],
            }
            source.write_text(yaml.safe_dump(doc))
            active = home / 'active.yaml'
            provider['config'].update({'id-token': 'new-id', 'refresh-token': 'new-refresh'})
            active.write_text(yaml.safe_dump(doc))
            self.assertEqual(resolver.resolve(home, active)['label'], 'DEV')

            provider['config']['client-id'] = 'different-client'
            active.write_text(yaml.safe_dump(doc))
            self.assertEqual(resolver.resolve(home, active)['reason'], 'connection-mismatch')

    def test_directories_overrides_duplicates_and_changes(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            root = home / '.kube/configs'
            source = root / 'lab/uat/fixture.yaml'
            source.parent.mkdir(parents=True)
            doc = dict(contexts=[dict(name='k3s-dev', context=dict(cluster='c', user='u'))],
                       clusters=[dict(name='c', cluster=dict(server='https://example.invalid'))],
                       users=[dict(name='u', user={})], **{'current-context': 'k3s-dev'})
            source.write_text(yaml.safe_dump(doc))
            active = home / 'active'
            active.write_text(source.read_text())
            (home / '.kube/kubie.yaml').write_text('configs:\n  include: ["~/.kube/configs/**/*.yaml"]\n')
            self.assertEqual(resolver.resolve(home, active)['environment'], 'uat')
            duplicate = source.with_name('duplicate.yaml')
            duplicate.write_text(source.read_text())
            self.assertEqual(resolver.resolve(home, active)['reason'], 'ambiguous-source')
            duplicate.unlink()
            policy = home / '.config/terminal-dotfiles/kube-environments.yaml'
            policy.parent.mkdir(parents=True)
            data = dict(environments={'custom':dict(label='CUSTOM',color='112233')}, overrides=[
                dict(source='lab/uat/fixture.yaml',context='k3s-dev',environment='custom')])
            policy.write_text(yaml.safe_dump(data))
            self.assertEqual(resolver.resolve(home, active)['environment'], 'custom')
            data['overrides'] *= 2
            policy.write_text(yaml.safe_dump(data))
            self.assertEqual(resolver.resolve(home, active)['reason'], 'conflicting-overrides')
            policy.unlink()
            doc['clusters'][0]['cluster']['server'] = 'https://different.invalid'
            active.write_text(yaml.safe_dump(doc))
            self.assertEqual(resolver.resolve(home, active)['reason'], 'connection-mismatch')

    def test_exclusions_aliases_and_invalid_profiles(self):
        with TemporaryDirectory() as temp:
            home = Path(temp)
            source = home / '.kube/configs/corp/company/development/a.yaml'
            source.parent.mkdir(parents=True)
            document = {'current-context': 'arbitrary', 'contexts': [{'name': 'arbitrary', 'context': {'cluster': 'c', 'user': 'u'}}],
                        'clusters': [{'name': 'c', 'cluster': {'server': 'https://example.invalid'}}], 'users': [{'name': 'u', 'user': {}}]}
            source.write_text(yaml.safe_dump(document))
            active = home / 'active'
            active.write_text(source.read_text())
            config = home / '.kube/kubie.yaml'
            config.write_text('configs:\n  include: ["~/.kube/configs/**/*.yaml"]\n')
            policy = home / '.config/terminal-dotfiles/kube-environments.yaml'
            policy.parent.mkdir(parents=True)
            policy.write_text('directory_aliases: {development: dev}\n')
            self.assertEqual(resolver.resolve(home, active)['environment'], 'dev')
            config.write_text('configs:\n  include: ["~/.kube/configs/**/*.yaml"]\n  exclude: ["~/.kube/configs/corp/**/*.yaml"]\n')
            self.assertEqual(resolver.resolve(home, active)['reason'], 'missing-source')
            config.write_text('configs:\n  include: ["~/.kube/configs/**/*.yaml"]\n')
            policy.write_text('environments: {}\nenvironments: {}\n')
            self.assertEqual(resolver.resolve(home, active)['reason'], 'invalid-configuration')

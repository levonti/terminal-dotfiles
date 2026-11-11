"""Local Kubernetes environment metadata. Never connects to a cluster."""
import glob
import json
import os
from pathlib import Path
import re
import sys
import yaml

DEFAULTS = {k: dict(label=k.upper(), color=v) for k, v in
            [('dev', 'a3be8c'), ('test', 'ebcb8b'), ('prod', 'ed8796'),
             ('uat', '88c0d0'), ('nt', 'b48ead')]}
CATEGORY_DEPTHS = {'lab': 3, 'local': 3, 'corp': 4, 'public': 5}


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError('duplicate YAML key')
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read(path):
    with Path(path).open() as stream:
        return yaml.load(stream, Loader=UniqueLoader) or {}


def stable_user_config(user):
    provider = user.get('auth-provider') if isinstance(user, dict) else None
    if not isinstance(provider, dict) or provider.get('name') != 'oidc':
        return user
    config = provider.get('config')
    if not isinstance(config, dict):
        return user
    # client-go writes refreshed tokens back to Kubie's temporary kubeconfig.
    stable_config = {key: value for key, value in config.items() if key not in ('id-token', 'refresh-token')}
    return {**user, 'auth-provider': {**provider, 'config': stable_config}}


def resolve(home, active, settings=None):
    home = Path(home)
    result = dict(environment='?ENV', label='?ENV', color='c1a7d5', category='?CAT', reason='unmapped')
    def expand(value):
        return str(home / value[2:]) if value.startswith('~/') else value
    try:
        policy_path = home / '.config/terminal-dotfiles/kube-environments.yaml'
        policy = read(policy_path) if policy_path.exists() else {}
        profiles = policy.get('environments', DEFAULTS)
        aliases = policy.get('directory_aliases', {})
        root = Path(expand(policy.get('root', '~/.kube/configs'))).resolve()
        current = read(active)
        name = current.get('current-context', '')
        context = next(c['context'] for c in current['contexts'] if c['name'] == name)
        result.update(context=name, namespace=context.get('namespace', ''))
        config_path = Path(settings or home / '.kube/kubie.yaml')
        config = read(config_path) if config_path.exists() else {}
        patterns = config.get('configs', {}).get('include', [
            '~/.kube/config', '~/.kube/*.yml', '~/.kube/*.yaml',
            '~/.kube/configs/*.yml', '~/.kube/configs/*.yaml',
            '~/.kube/kubie/*.yml', '~/.kube/kubie/*.yaml'])
        excluded = {config_path.resolve()}
        for pattern in config.get('configs', {}).get('exclude', []):
            excluded.update(Path(p).resolve() for p in glob.glob(expand(pattern), recursive=True))
        paths = {Path(p).resolve() for pattern in patterns
                 for p in glob.glob(expand(pattern), recursive=True)} - excluded
        matches = []
        for path in sorted(paths):
            document = read(path)
            for entry in document.get('contexts', []):
                if entry['name'] == name:
                    matches.append((path, document, entry['context']))
        if len(matches) != 1:
            result['reason'] = 'missing-source' if not matches else 'ambiguous-source'
            return result
        path, document, original = matches[0]
        # Context names alone must not identify a different active connection.
        for section, field, payload in [('clusters', 'cluster', 'cluster'), ('users', 'user', 'user')]:
            def item(doc, ctx):
                value = next(x[payload] for x in doc[section] if x['name'] == ctx[field])
                return stable_user_config(value) if field == 'user' else value
            if item(current, context) != item(document, original):
                result['reason'] = 'connection-mismatch'
                return result
        relative = path.relative_to(root).as_posix() if path.is_relative_to(root) else str(path)
        result['source'] = relative
        parts = Path(relative).parts
        depth = CATEGORY_DEPTHS.get(parts[0]) if len(parts) > 1 else None
        if depth is not None:
            result['category'] = parts[0].upper()
        overrides = [x['environment'] for x in policy.get('overrides', [])
                     if x['source'] == relative and x['context'] == name]
        if len(overrides) > 1:
            result['reason'] = 'conflicting-overrides'
            return result
        env = overrides[0] if overrides else aliases.get(parts[-2], parts[-2]) if len(parts) == depth else None
        profile = profiles.get(env)
        if not profile:
            return result
        label, color = profile['label'], profile['color'].lstrip('#')
        if not re.fullmatch(r'[A-Z0-9?_-]{1,12}', label) or not re.fullmatch(r'[0-9a-fA-F]{6}', color):
            raise ValueError('invalid profile')
        context_labels = policy.get('context_labels', {})
        short_name = context_labels.get(name) if isinstance(context_labels, dict) else None
        if isinstance(short_name, str) and short_name.isprintable() and short_name.strip():
            result['context_label'] = short_name.strip()
        result.update(environment=env, label=label, color=color,
                      reason='override' if overrides else 'directory')
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError, StopIteration, yaml.YAMLError):
        result['reason'] = 'invalid-configuration'
    return result


def main():
    if not os.environ.get('KUBIE_ACTIVE'):
        return
    active = os.environ.get('KUBECONFIG', '')
    if not active or active != os.environ.get('KUBIE_KUBECONFIG', active):
        return
    state = resolve(Path.home(), active)
    # Only printable text is ever sent to terminal consumers.
    context = ''.join(c for c in state.get('context_label', state.get('context', '')) if c.isprintable())
    namespace = ''.join(c for c in state.get('namespace', '') if c.isprintable())
    suffix = ' / ' + namespace if namespace else ''
    if '--json' in sys.argv:
        print(json.dumps(state))
    elif '--state' in sys.argv:
        print(state['label'] + '\t' + state['color'] + '\t' + context + suffix)
        if '--with-category' in sys.argv:
            print(state['category'] + '\t' + namespace)
    elif context:
        rgb = ';'.join(str(int(state['color'][i:i+2], 16)) for i in (0, 2, 4))
        badge = f'\033[1;38;2;23;27;36;48;2;{rgb}m[{state["label"]}]\033[0m'
        detail = f'\033[38;2;162;173;189m{suffix}\033[0m' if suffix else ''
        print(f'{badge} {state["category"]} {context}{detail}', end='')


if __name__ == '__main__':
    main()

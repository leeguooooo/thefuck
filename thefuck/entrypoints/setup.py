import os
import sys
import shutil
from getpass import getpass
import six
from ..conf import settings
from ..logs import warn
from ..shells import shell
from ..system import Path

# Use builtin input to avoid colorama wrapper issues
if six.PY2:
    _input = raw_input  # noqa: F821
else:
    import builtins
    _input = builtins.input


def _ask(prompt, default=None, secret=False):
    if default:
        prompt_text = '{} [{}]: '.format(prompt, default)
    else:
        prompt_text = '{}: '.format(prompt)
    if secret:
        value = getpass(prompt_text)
    else:
        value = _input(prompt_text)
    value = value.strip()
    if not value:
        return default
    return value


def _ask_bool(prompt, default):
    suffix = 'Y/n' if default else 'y/N'
    while True:
        value = _input('{} ({})? '.format(prompt, suffix)).strip().lower()
        if not value:
            return default
        if value in ('y', 'yes'):
            return True
        if value in ('n', 'no'):
            return False
        sys.stderr.write('Please enter y or n.\n')


def _ask_int(prompt, default):
    value = _ask(prompt, six.text_type(default))
    try:
        return int(value)
    except (TypeError, ValueError):
        warn('Invalid number, using default {}'.format(default))
        return default


def _normalize_mode(mode, default):
    if mode in ('prefer', 'fallback'):
        return mode
    warn("Unknown AI mode '{}', using {}".format(mode, default))
    return default


def _quote(value):
    return shell.quote(six.text_type(value))


def _is_fish():
    return shell.__class__.__name__.lower() == 'fish'


def _build_env_lines(values, fish):
    lines = []
    for key, value in values.items():
        if value is None:
            continue
        if fish:
            lines.append('set -gx {} {}'.format(key, _quote(value)))
        else:
            lines.append('export {}={}'.format(key, _quote(value)))
    return lines


def _shell_path(path, xdg_config_home, use_xdg):
    if use_xdg and xdg_config_home:
        xdg_root = Path(xdg_config_home, 'thefuck').expanduser()
        if path == xdg_root:
            return '$XDG_CONFIG_HOME/thefuck'
        if str(path).startswith(str(xdg_root) + os.sep):
            suffix = str(path)[len(str(xdg_root)) + 1:]
            return '$XDG_CONFIG_HOME/thefuck/{}'.format(suffix)
    home = Path('~').expanduser()
    if str(path).startswith(str(home) + os.sep):
        suffix = str(path)[len(str(home)) + 1:]
        return '$HOME/{}'.format(suffix)
    return str(path)


def _write_env_file(path, lines):
    with path.open(mode='w') as env_file:
        env_file.write('# thefuck env\n')
        for line in lines:
            env_file.write(line + '\n')


def _build_path_lines(bin_path, fish):
    if fish:
        return ['set -gx PATH {} $PATH'.format(bin_path)]
    return ['export PATH="{}:$PATH"'.format(bin_path)]


def _write_wrapper(path):
    content = (
        '#!/bin/sh\n'
        'if [ -n "$THEFUCK_PROJECT_PATH" ]; then\n'
        '  exec uv run --project "$THEFUCK_PROJECT_PATH" thefuck "$@"\n'
        'fi\n'
        'if command -v uvx >/dev/null 2>&1; then\n'
        '  exec uvx thefuck "$@"\n'
        'fi\n'
        'exec uv run thefuck "$@"\n'
    )
    with path.open(mode='w') as script_file:
        script_file.write(content)
    os.chmod(str(path), 0o755)


def setup():
    print('Setup:')
    print('Press enter to keep the default value shown in brackets.')

    xdg_config_home_env = os.environ.get('XDG_CONFIG_HOME')
    xdg_config_home = xdg_config_home_env or '~/.config'
    use_xdg = xdg_config_home_env is not None
    config_root = Path(xdg_config_home, 'thefuck').expanduser()
    legacy_root = Path('~/.thefuck').expanduser()
    if legacy_root.is_dir() and legacy_root != config_root:
        if _ask_bool(
                'Legacy config found at {}. Migrate to {}'
                .format(legacy_root, config_root),
                True):
            try:
                if not config_root.parent.is_dir():
                    config_root.parent.mkdir(parents=True)
                shutil.move(str(legacy_root), str(config_root))
            except OSError as exc:
                warn('Failed to migrate config: {}'.format(exc))
                config_root = legacy_root
        else:
            config_root = legacy_root
    bin_dir = config_root.joinpath('bin')
    fish = _is_fish()
    env_path = config_root.joinpath('env.fish' if fish else 'env.sh')
    env_path_shell = _shell_path(env_path, xdg_config_home, use_xdg)
    bin_path_shell = _shell_path(bin_dir, xdg_config_home, use_xdg)

    if not config_root.is_dir():
        config_root.mkdir(parents=True)
    if not bin_dir.is_dir():
        bin_dir.mkdir(parents=True)

    settings.init()
    defaults = {
        'ai_enabled': settings.ai_enabled,
        'ai_url': settings.ai_url,
        'ai_token': settings.ai_token,
        'ai_model': settings.ai_model,
        'ai_timeout': settings.ai_timeout,
        'ai_reasoning_effort': settings.ai_reasoning_effort,
        'ai_stream': settings.ai_stream,
        'ai_mode': settings.ai_mode,
        'ai_stream_output': settings.ai_stream_output
    }

    ai_enabled = _ask_bool('Enable AI', defaults['ai_enabled'])
    values = {
        'THEFUCK_AI_ENABLED': 'true' if ai_enabled else 'false'
    }

    if ai_enabled:
        ai_url = _ask('AI URL', defaults['ai_url'])
        ai_token = _ask('AI token', defaults['ai_token'], secret=False)
        ai_model = _ask('AI model', defaults['ai_model'])
        ai_timeout = _ask_int('Timeout seconds', defaults['ai_timeout'])
        ai_reasoning_effort = _ask(
            'Reasoning effort (low/medium/high)',
            defaults['ai_reasoning_effort'])
        ai_stream = _ask_bool('Use SSE stream', defaults['ai_stream'])
        ai_stream_output = _ask_bool(
            'Stream output while waiting', defaults['ai_stream_output'])
        ai_mode = _normalize_mode(
            _ask('AI mode (prefer/fallback)', defaults['ai_mode']),
            defaults['ai_mode'])

        values.update({
            'THEFUCK_AI_URL': ai_url,
            'THEFUCK_AI_TOKEN': ai_token,
            'THEFUCK_AI_MODEL': ai_model,
            'THEFUCK_AI_TIMEOUT': ai_timeout,
            'THEFUCK_AI_REASONING_EFFORT': ai_reasoning_effort,
            'THEFUCK_AI_STREAM': 'true' if ai_stream else 'false',
            'THEFUCK_AI_MODE': ai_mode,
            'THEFUCK_AI_STREAM_OUTPUT': 'true' if ai_stream_output else 'false'
        })

    env_lines = _build_path_lines(bin_path_shell, fish)
    env_lines.extend(_build_env_lines(values, fish))
    _write_env_file(env_path, env_lines)
    _write_wrapper(bin_dir.joinpath('thefuck'))

    print('\nWrote env file:', env_path)
    print('Wrote wrapper:', bin_dir.joinpath('thefuck'))
    print('\nAdd to your shell config:')
    print('source {}'.format(env_path_shell))
    print('\nOptional for local development:')
    print('set THEFUCK_PROJECT_PATH to use a local checkout with uv run')

    config = shell.how_to_configure()
    if config and _ask_bool(
            'Append setup to {}'.format(config.path), False):
        path = os.path.expanduser(config.path)
        try:
            with open(path, 'a') as config_file:
                config_file.write('\n# thefuck config\n')
                config_file.write('source {}\n'.format(env_path_shell))
            print('Done. Run: {}'.format(config.reload))
        except OSError as exc:
            warn('Failed to write {}: {}'.format(path, exc))

from time import time
import os
from subprocess import Popen, PIPE
from tempfile import gettempdir
from uuid import uuid4
from ..conf import settings
from ..const import ARGUMENT_PLACEHOLDER, USER_COMMAND_MARK
from ..utils import DEVNULL, memoize, get_installation_version
from .generic import Generic


class Zsh(Generic):
    friendly_name = 'ZSH'
    _alias_version = get_installation_version()

    def app_alias(self, alias_name):
        # It is VERY important to have the variables declared WITHIN the function
        return '''
            {name} () {{
                FUCK_PYTHONIOENCODING=$PYTHONIOENCODING;
                if [ "$1" = "setup" ] || [ "$1" = "--setup" ] || [ "$1" = "ai-setup" ] \
                    || [ "$1" = "--alias" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ] \
                    || [ "$1" = "-v" ] || [ "$1" = "--version" ]; then
                    command fuck "$@";
                    return $?;
                fi
                export FUCK_SHELL=zsh;
                export FUCK_ALIAS={name};
                export FUCK_ALIAS_VERSION="{alias_version}";
                FUCK_SHELL_ALIASES=$(alias);
                export FUCK_SHELL_ALIASES;
                FUCK_HISTORY="$(fc -ln -10)";
                export FUCK_HISTORY;
                export FUCK_PROMPT="$*";
                export PYTHONIOENCODING=utf-8;
                FUCK_CMD=$(
                    command fuck {argument_placeholder} $@
                ) && eval $FUCK_CMD;
                unset FUCK_HISTORY;
                unset FUCK_PROMPT;
                export PYTHONIOENCODING=$FUCK_PYTHONIOENCODING;
                {alter_history}
            }}
        '''.format(
            name=alias_name,
            argument_placeholder=ARGUMENT_PLACEHOLDER,
            alias_version=self._alias_version,
            alter_history=('test -n "$FUCK_CMD" && print -s $FUCK_CMD'
                           if settings.alter_history else ''))

    def instant_mode_alias(self, alias_name):
        if os.environ.get('FUCK_INSTANT_MODE', '').lower() == 'true':
            mark = ('%{' +
                    USER_COMMAND_MARK + '\b' * len(USER_COMMAND_MARK)
                    + '%}')
            return '''
                export PS1="{user_command_mark}$PS1";
                {app_alias}
            '''.format(user_command_mark=mark,
                       app_alias=self.app_alias(alias_name))
        else:
            log_path = os.path.join(
                gettempdir(), 'fuck-script-log-{}'.format(uuid4().hex))
            return '''
                export FUCK_INSTANT_MODE=True;
                export FUCK_OUTPUT_LOG={log};
                command fuck --shell-logger {log};
                rm -f {log};
                exit
            '''.format(log=log_path)

    def _parse_alias(self, alias):
        name, value = alias.split('=', 1)
        if value[0] == value[-1] == '"' or value[0] == value[-1] == "'":
            value = value[1:-1]
        return name, value

    @memoize
    def get_aliases(self):
        raw_aliases = os.environ.get('FUCK_SHELL_ALIASES', '').split('\n')
        return dict(self._parse_alias(alias)
                    for alias in raw_aliases if alias and '=' in alias)

    def _get_history_file_name(self):
        return os.environ.get("HISTFILE",
                              os.path.expanduser('~/.zsh_history'))

    def _get_history_line(self, command_script):
        return u': {}:0;{}\n'.format(int(time()), command_script)

    def _script_from_history(self, line):
        if ';' in line:
            return line.split(';', 1)[1]
        else:
            return ''

    def how_to_configure(self):
        candidates = []
        zdotdir = os.environ.get('ZDOTDIR')
        if zdotdir:
            candidates.append(
                os.path.join(os.path.expanduser(zdotdir), '.zshrc'))
        candidates.extend(['~/.zshrc', '~/.zprofile', '~/.zshenv'])
        config = next(
            (path for path in candidates
             if os.path.isfile(os.path.expanduser(path))),
            candidates[0])

        return self._create_shell_configuration(
            content=self._env_source(),
            path=config,
            reload='source {}'.format(config))

    def _get_version(self):
        """Returns the version of the current shell"""
        proc = Popen(['zsh', '-c', 'echo $ZSH_VERSION'],
                     stdout=PIPE, stderr=DEVNULL)
        return proc.stdout.read().decode('utf-8').strip()

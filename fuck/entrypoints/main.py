# Initialize output before importing any module, that can use colorama.
from ..system import init_output

init_output()

import os  # noqa: E402
import sys  # noqa: E402
from .. import logs  # noqa: E402
from ..argument_parser import Parser  # noqa: E402
from ..utils import get_installation_version  # noqa: E402
from ..shells import shell  # noqa: E402
from .alias import print_alias  # noqa: E402
from .fix_command import fix_command  # noqa: E402
from .not_configured import main as not_configured_main  # noqa: E402
from .setup import setup  # noqa: E402


def _is_setup_command(known_args):
    if getattr(known_args, 'setup', False):
        return True
    return bool(known_args.command and known_args.command[0] in (
        'setup', 'ai-setup'))


def _called_via_alias():
    return bool(os.environ.get('FUCK_PROMPT') or
                os.environ.get('FUCK_COMMAND') or
                os.environ.get('FUCK_HISTORY'))


def main():
    parser = Parser()
    known_args = parser.parse(sys.argv)

    if known_args.help:
        parser.print_help()
    elif known_args.version:
        logs.version(get_installation_version(),
                     sys.version.split()[0], shell.info())
    # It's important to check if an alias is being requested before checking if
    # `FUCK_HISTORY` is in `os.environ`, otherwise it might mess with subshells.
    # Check https://github.com/leeguooooo/fuck/issues/921 for reference
    elif known_args.alias:
        print_alias(known_args)
    elif _is_setup_command(known_args):
        if _called_via_alias():
            if known_args.setup:
                print('command fuck --setup')
            else:
                setup_cmd = ' '.join(known_args.command)
                print('command fuck {}'.format(setup_cmd))
            return
        setup()
    elif known_args.command or 'FUCK_HISTORY' in os.environ:
        fix_command(known_args)
    elif known_args.shell_logger:
        try:
            from .shell_logger import shell_logger  # noqa: E402
        except ImportError:
            logs.warn('Shell logger supports only Linux and macOS')
        else:
            shell_logger(known_args.shell_logger)
    else:
        not_configured_main()

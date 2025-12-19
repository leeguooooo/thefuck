# Initialize output before importing any module, that can use colorama.
from ..system import init_output

init_output()

import getpass  # noqa: E402
import os  # noqa: E402
import json  # noqa: E402
import sys  # noqa: E402
import subprocess  # noqa: E402
from tempfile import gettempdir  # noqa: E402
import time  # noqa: E402
import six  # noqa: E402
from psutil import Process  # noqa: E402
from .. import logs, const, types  # noqa: E402
from ..shells import shell  # noqa: E402
from ..conf import settings  # noqa: E402
from ..system import Path  # noqa: E402
from ..corrector import get_corrected_commands  # noqa: E402
from ..exceptions import EmptyCommand  # noqa: E402


def _get_shell_pid():
    """Returns parent process pid."""
    proc = Process(os.getpid())

    try:
        return proc.parent().pid
    except TypeError:
        return proc.parent.pid


def _get_not_configured_usage_tracker_path():
    """Returns path of special file where we store latest shell pid."""
    return Path(gettempdir()).joinpath(u'thefuck.last_not_configured_run_{}'.format(
        getpass.getuser(),
    ))


def _record_first_run():
    """Records shell pid to tracker file."""
    info = {'pid': _get_shell_pid(),
            'time': time.time()}

    mode = 'wb' if six.PY2 else 'w'
    with _get_not_configured_usage_tracker_path().open(mode) as tracker:
        json.dump(info, tracker)


def _get_previous_command():
    history = shell.get_history()

    if history:
        return history[-1]
    else:
        return None


def _is_second_run():
    """Returns `True` when we know that `fuck` called second time."""
    tracker_path = _get_not_configured_usage_tracker_path()
    if not tracker_path.exists():
        return False

    current_pid = _get_shell_pid()
    with tracker_path.open('r') as tracker:
        try:
            info = json.load(tracker)
        except ValueError:
            return False

    if not (isinstance(info, dict) and info.get('pid') == current_pid):
        return False

    return (_get_previous_command() == 'fuck' or
            time.time() - info.get('time', 0) < const.CONFIGURATION_TIMEOUT)


def _is_already_configured(configuration_details):
    """Returns `True` when alias already in shell config."""
    path = Path(configuration_details.path).expanduser()
    with path.open('r') as shell_config:
        return configuration_details.content in shell_config.read()


def _configure(configuration_details):
    """Adds alias to shell config."""
    path = Path(configuration_details.path).expanduser()
    with path.open('a') as shell_config:
        shell_config.write(u'\n')
        shell_config.write(configuration_details.content)
        shell_config.write(u'\n')


def _get_last_command_from_history():
    """Gets the last command from shell history, excluding 'fuck' itself."""
    history = shell.get_history()
    if not history:
        return None
    
    # Find the last command that isn't 'fuck'
    for cmd in reversed(history):
        cmd_stripped = cmd.strip()
        if cmd_stripped and cmd_stripped != 'fuck' and not cmd_stripped.startswith('fuck '):
            return cmd_stripped
    return None


def _run_and_fix_command(command_script):
    """Runs the command and tries to fix it."""
    try:
        command = types.Command.from_raw_script([command_script])
    except EmptyCommand:
        logs.debug('Empty command, nothing to do')
        return False

    corrected_commands = get_corrected_commands(command)
    
    # Get the first corrected command
    selected_command = None
    for cmd in corrected_commands:
        selected_command = cmd
        break
    
    if selected_command:
        # Print the fixed command
        fixed_script = selected_command.script
        print(u'\nSuggested fix: {}'.format(fixed_script))
        
        # Ask for confirmation
        try:
            if six.PY2:
                response = raw_input('Run this command? [Y/n] ')  # noqa: F821
            else:
                response = input('Run this command? [Y/n] ')
            if response.lower() in ('', 'y', 'yes'):
                subprocess.call(fixed_script, shell=True)
                return True
        except (KeyboardInterrupt, EOFError):
            print('')
        return True
    return False


def _auto_configure_shell():
    """Automatically configures the shell if possible."""
    configuration_details = shell.how_to_configure()
    if (configuration_details and 
        configuration_details.can_configure_automatically and
        not _is_already_configured(configuration_details)):
        _configure(configuration_details)
        return True
    return False


def main():
    """Main entry point for 'fuck' command.
    
    This now works in two modes:
    1. If shell alias is configured: works through the alias (fast mode)
    2. If not configured: reads history, reruns command, and fixes it
    
    Also auto-configures the shell for better experience next time.
    """
    settings.init()
    
    # Check if we're being called through the alias (TF_COMMAND is set)
    if os.environ.get('TF_COMMAND'):
        # We're being called through alias, delegate to fix_command
        from .fix_command import fix_command
        from ..argument_parser import Parser
        parser = Parser()
        known_args = parser.parse(sys.argv)
        fix_command(known_args)
        return
    
    # Not called through alias - work directly with history
    last_command = _get_last_command_from_history()
    
    if not last_command:
        logs.how_to_configure_alias(shell.how_to_configure())
        return
    
    # Try to fix the command
    print(u'Last command: {}'.format(last_command))
    print(u'Re-running to get output...')
    
    if _run_and_fix_command(last_command):
        # Auto-configure shell for next time
        if _auto_configure_shell():
            print(u'\nShell configured! Restart your terminal for faster experience.')
    else:
        print(u'No fix found for this command.')
        
        # Show configuration help
        configuration_details = shell.how_to_configure()
        if configuration_details:
            if _auto_configure_shell():
                print(u'\nShell auto-configured! Restart your terminal.')
            else:
                logs.how_to_configure_alias(configuration_details)

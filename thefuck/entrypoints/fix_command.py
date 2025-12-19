from pprint import pformat
import os
import sys
from difflib import SequenceMatcher
from itertools import chain
from .. import logs, types, const
from ..conf import settings
from ..corrector import get_corrected_commands
from ..exceptions import EmptyCommand
from ..ui import select_command
from ..utils import format_raw_script, get_alias, get_all_executables
from ..ai import (build_corrected_commands, emit_markdown,
                  fallback_corrected_commands, get_ai_suggestion, is_enabled)


def _get_raw_command(known_args):
    if known_args.force_command:
        return [known_args.force_command]
    tf_command = os.environ.get('TF_COMMAND')
    if tf_command:
        return [tf_command]
    elif not os.environ.get('TF_HISTORY'):
        return known_args.command
    else:
        history = os.environ['TF_HISTORY'].split('\n')[::-1]
        alias = get_alias()
        executables = get_all_executables()
        for command in history:
            diff = SequenceMatcher(a=alias, b=command).ratio()
            if diff < const.DIFF_WITH_ALIAS or command in executables:
                return [command]
    return []


def _get_ai_prompt(known_args):
    env_prompt = os.environ.get('TF_PROMPT', '').strip()
    if env_prompt:
        return env_prompt
    if not os.environ.get('TF_HISTORY'):
        return
    prompt = format_raw_script(known_args.command)
    return prompt or None


def fix_command(known_args):
    """Fixes previous command. Used when `thefuck` called without arguments."""
    settings.init(known_args)
    with logs.debug_time('Total'):
        logs.debug(u'Run with settings: {}'.format(pformat(settings)))
        raw_command = _get_raw_command(known_args)

        try:
            command = types.Command.from_raw_script(raw_command)
        except EmptyCommand:
            logs.debug('Empty command, nothing to do')
            return

        corrected_commands = get_corrected_commands(command)
        ai_prompt = _get_ai_prompt(known_args)
        if is_enabled():
            if ai_prompt:
                ai_result = get_ai_suggestion(
                    command, prompt=ai_prompt, warn_on_error=True)
                if ai_result:
                    if ai_result.explanation and not ai_result.streamed:
                        emit_markdown(ai_result.explanation)
                        ai_result = ai_result._replace(streamed=True)
                    if ai_result.commands:
                        corrected_commands = iter(
                            build_corrected_commands(ai_result))
                    elif ai_result.explanation and not ai_result.streamed:
                        emit_markdown(ai_result.explanation)
                        sys.exit(1)
                    else:
                        sys.exit(1)
            elif settings.ai_mode == 'prefer':
                ai_result = get_ai_suggestion(command)
                if ai_result:
                    if ai_result.commands:
                        ai_commands = build_corrected_commands(ai_result)
                        corrected_commands = chain(ai_commands,
                                                   corrected_commands)
                    elif ai_result.explanation:
                        emit_markdown(ai_result.explanation)
            else:
                corrected_commands, ai_result = fallback_corrected_commands(
                    command, corrected_commands)
                if ai_result and not ai_result.commands and ai_result.explanation:
                    emit_markdown(ai_result.explanation)
                    sys.exit(1)
        selected_command = select_command(corrected_commands)

        if selected_command:
            selected_command.run(command)
        else:
            sys.exit(1)

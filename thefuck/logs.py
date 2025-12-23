# -*- encoding: utf-8 -*-

from contextlib import contextmanager
from datetime import datetime
import os
import re
import sys
import unicodedata
from traceback import format_exception
import colorama
try:
    from shutil import get_terminal_size
except ImportError:  # pragma: no cover - Python < 3.3
    from backports.shutil_get_terminal_size import get_terminal_size
from .conf import settings
from . import const


def color(color_):
    """Utility for ability to disabling colored output."""
    if settings.no_colors:
        return ''
    else:
        return color_


_ANSI_RE = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
_last_confirm_lines = 0


def _strip_ansi(text):
    return _ANSI_RE.sub('', text)


def _terminal_columns():
    try:
        return os.get_terminal_size(sys.stderr.fileno()).columns or 80
    except Exception:
        cols = get_terminal_size((80, 20)).columns or 80
        return cols


def _text_width(text):
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            width += 2
        else:
            width += 1
    return width


def _calc_prompt_lines(text):
    cols = _terminal_columns()
    if cols <= 0:
        cols = 80
    visible = _strip_ansi(text.replace(const.USER_COMMAND_MARK, ''))
    if not visible:
        return 1
    total = 0
    for line in visible.splitlines() or ['']:
        width = _text_width(line)
        total += max(1, (width - 1) // cols + 1)
    return total


def _clear_previous_confirm():
    if _last_confirm_lines <= 0:
        return ''
    seq = '\r'
    for idx in range(_last_confirm_lines):
        seq += '\033[2K'
        if idx < _last_confirm_lines - 1:
            seq += '\033[1A'
    return seq + '\r'


def reset_confirm_text():
    global _last_confirm_lines
    _last_confirm_lines = 0


def warn(title):
    sys.stderr.write(u'{warn}[WARN] {title}{reset}\n'.format(
        warn=color(colorama.Back.RED + colorama.Fore.WHITE
                   + colorama.Style.BRIGHT),
        reset=color(colorama.Style.RESET_ALL),
        title=title))


def exception(title, exc_info):
    sys.stderr.write(
        u'{warn}[WARN] {title}:{reset}\n{trace}'
        u'{warn}----------------------------{reset}\n\n'.format(
            warn=color(colorama.Back.RED + colorama.Fore.WHITE
                       + colorama.Style.BRIGHT),
            reset=color(colorama.Style.RESET_ALL),
            title=title,
            trace=''.join(format_exception(*exc_info))))


def rule_failed(rule, exc_info):
    exception(u'Rule {}'.format(rule.name), exc_info)


def failed(msg):
    sys.stderr.write(u'{red}{msg}{reset}\n'.format(
        msg=msg,
        red=color(colorama.Fore.RED),
        reset=color(colorama.Style.RESET_ALL)))


def show_corrected_command(corrected_command):
    desc = getattr(corrected_command, 'desc', '') or ''
    desc = u' '.join(desc.split())
    desc_output = ''
    if desc:
        desc_output = u' — {desc_color}{desc}{reset}'.format(
            desc_color=color(colorama.Fore.YELLOW),
            desc=desc,
            reset=color(colorama.Style.RESET_ALL))
    sys.stderr.write(
        u'{prefix}{cmd_color}{script}{reset}{desc_output}{side_effect}\n'.format(
            prefix=const.USER_COMMAND_MARK,
            script=corrected_command.script,
            desc_output=desc_output,
            side_effect=u' (+side effect)' if corrected_command.side_effect else u'',
            cmd_color=color(colorama.Style.BRIGHT + colorama.Fore.CYAN),
            reset=color(colorama.Style.RESET_ALL)))


def confirm_text(corrected_command):
    global _last_confirm_lines
    desc = getattr(corrected_command, 'desc', '') or ''
    desc = u' '.join(desc.split())
    desc_output = ''
    if desc:
        desc_output = u' — {desc_color}{desc}{reset}'.format(
            desc_color=color(colorama.Fore.YELLOW),
            desc=desc,
            reset=color(colorama.Style.RESET_ALL))
    prompt = (u'{prefix}{cmd_color}{script}{reset}{desc_output}{side_effect} '
              u'[{green}enter{reset}/{blue}↑{reset}/{blue}↓{reset}'
              u'/{blue}tab{reset}/{red}ctrl+c{reset}]').format(
                  prefix=const.USER_COMMAND_MARK,
                  script=corrected_command.script,
                  desc_output=desc_output,
                  side_effect=' (+side effect)' if corrected_command.side_effect else '',
                  cmd_color=color(colorama.Style.BRIGHT + colorama.Fore.CYAN),
                  green=color(colorama.Fore.GREEN),
                  red=color(colorama.Fore.RED),
                  reset=color(colorama.Style.RESET_ALL),
                  blue=color(colorama.Fore.BLUE))
    sys.stderr.write(_clear_previous_confirm())
    sys.stderr.write(prompt)
    sys.stderr.flush()
    _last_confirm_lines = _calc_prompt_lines(prompt)


def debug(msg):
    if settings.debug:
        sys.stderr.write(u'{blue}{bold}DEBUG:{reset} {msg}\n'.format(
            msg=msg,
            reset=color(colorama.Style.RESET_ALL),
            blue=color(colorama.Fore.BLUE),
            bold=color(colorama.Style.BRIGHT)))


@contextmanager
def debug_time(msg):
    started = datetime.now()
    try:
        yield
    finally:
        debug(u'{} took: {}'.format(msg, datetime.now() - started))


def how_to_configure_alias(configuration_details):
    print(u"Seems like {bold}fuck{reset} alias isn't configured!".format(
        bold=color(colorama.Style.BRIGHT),
        reset=color(colorama.Style.RESET_ALL)))

    if configuration_details:
        print(
            u"Please put {bold}{content}{reset} in your "
            u"{bold}{path}{reset} and apply "
            u"changes with {bold}{reload}{reset} or restart your shell.".format(
                bold=color(colorama.Style.BRIGHT),
                reset=color(colorama.Style.RESET_ALL),
                **configuration_details._asdict()))

        if configuration_details.can_configure_automatically:
            print(
                u"Or run {bold}fuck{reset} a second time to configure"
                u" it automatically.".format(
                    bold=color(colorama.Style.BRIGHT),
                    reset=color(colorama.Style.RESET_ALL)))

    print(u'More details - https://github.com/nvbn/thefuck#manual-installation')


def already_configured(configuration_details):
    print(
        u"Seems like {bold}fuck{reset} alias already configured!\n"
        u"For applying changes run {bold}{reload}{reset}"
        u" or restart your shell.".format(
            bold=color(colorama.Style.BRIGHT),
            reset=color(colorama.Style.RESET_ALL),
            reload=configuration_details.reload))


def configured_successfully(configuration_details):
    print(
        u"{bold}fuck{reset} alias configured successfully!\n"
        u"For applying changes run {bold}{reload}{reset}"
        u" or restart your shell.".format(
            bold=color(colorama.Style.BRIGHT),
            reset=color(colorama.Style.RESET_ALL),
            reload=configuration_details.reload))


def version(thefuck_version, python_version, shell_info):
    sys.stderr.write(
        u'The Fuck {} using Python {} and {}\n'.format(thefuck_version,
                                                       python_version,
                                                       shell_info))

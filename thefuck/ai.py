import json
import re
import sys
from collections import namedtuple
from itertools import chain
import colorama
import six
from six.moves.urllib import request
from six.moves.urllib.error import HTTPError, URLError

from . import const, logs
from .conf import settings
from .types import CorrectedCommand


AiResult = namedtuple('AiResult', [
    'commands', 'explanation', 'streamed', 'descriptions'
])


SYSTEM_PROMPT = """You are a CLI command correction assistant.

IMPORTANT: Use proper spacing between all words in your response.

Reply format:

think: [1-2 sentence explanation with normal word spacing]

answer: [JSON object]

JSON schema:
{"primary": {"command": "...", "desc": "..."}, "alternatives": [{"command": "...", "desc": "..."}]}

Rules:
1. Commands must be exact shell commands with correct spacing
2. Description must use normal English with spaces between words
3. If unsure, use empty command ""

Example:

think: The command gti is a typo for git.

answer: {"primary": {"command": "git status", "desc": "Show repository status"}, "alternatives": []}"""


_CJK_RE = re.compile(
    u'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]')


def is_enabled():
    return bool(settings.ai_enabled and settings.ai_url)


def _has_cjk(text):
    if not text:
        return False
    return bool(_CJK_RE.search(six.text_type(text)))


def _language_instruction(command, prompt):
    samples = [
        getattr(command, 'script', None),
        getattr(command, 'output', None),
        prompt,
    ]
    if any(_has_cjk(sample) for sample in samples if sample):
        return 'Respond in Chinese.'
    return 'Respond in English.'


def _build_ai_theme():
    from rich.theme import Theme
    return Theme({
        'ai.label': 'bold green',
        'ai.text': 'white',
        'ai.heading': 'bold green',
        'ai.command': 'bold cyan',
        'ai.desc': 'yellow',
        'ai.punct': 'yellow',
        'markdown': 'white',
    })


def emit_ai_result(result):
    if not result:
        return

    explanation = result.explanation or ''
    commands = result.commands or []
    descriptions = result.descriptions or {}
    if not explanation and not commands:
        return

    think_text = _strip_commands_section(explanation)
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        from rich.text import Text
    except Exception:
        _emit_ai_plain(think_text, commands, descriptions, numbered=True)
        return

    console = Console(stderr=True, theme=_build_ai_theme())
    console.print('AI:', style='ai.label')
    if think_text:
        console.print(Markdown(think_text), style='ai.text')
    if commands:
        console.print()
        console.print('Commands', style='ai.heading')
        for idx, cmd in enumerate(commands, 1):
            line = Text()
            line.append('{}. '.format(idx), style='ai.punct')
            line.append(cmd, style='ai.command')
            desc = descriptions.get(cmd, '')
            if desc:
                line.append(' — ', style='ai.punct')
                line.append(desc, style='ai.desc')
            console.print(line)


def emit_ai_commands(result):
    if not result:
        return
    commands = result.commands or []
    if not commands:
        return
    descriptions = result.descriptions or {}
    try:
        from rich.console import Console
        from rich.text import Text
    except Exception:
        _emit_ai_plain('', commands, descriptions, numbered=True)
        return

    console = Console(stderr=True, theme=_build_ai_theme())
    console.print()
    console.print('Commands', style='ai.heading')
    for idx, cmd in enumerate(commands, 1):
        line = Text()
        line.append('{}. '.format(idx), style='ai.punct')
        line.append(cmd, style='ai.command')
        desc = descriptions.get(cmd, '')
        if desc:
            line.append(' — ', style='ai.punct')
            line.append(desc, style='ai.desc')
        console.print(line)


def _emit_ai_plain(text, commands, descriptions, numbered=False):
    label = logs.color(colorama.Style.BRIGHT + colorama.Fore.GREEN)
    body = logs.color(colorama.Fore.WHITE)
    cmd_color = logs.color(colorama.Style.BRIGHT + colorama.Fore.CYAN)
    desc_color = logs.color(colorama.Fore.YELLOW)
    punct = logs.color(colorama.Fore.YELLOW)
    reset = logs.color(colorama.Style.RESET_ALL)

    if text or commands:
        sys.stderr.write(u'{label}AI:{reset}\n'.format(
            label=label, reset=reset))
    if text:
        sys.stderr.write(u'{body}{text}{reset}\n'.format(
            body=body, text=text, reset=reset))
    if commands:
        sys.stderr.write(u'\n{body}Commands{reset}\n'.format(
            body=body, reset=reset))
        for idx, cmd in enumerate(commands, 1):
            prefix = u'{}. '.format(idx) if numbered else u''
            line = u'{punct}{prefix}{reset}{cmd_color}{cmd}{reset}'.format(
                punct=punct, prefix=prefix, reset=reset,
                cmd_color=cmd_color, cmd=cmd)
            desc = descriptions.get(cmd, '')
            if desc:
                line += u' — {desc_color}{desc}{reset}'.format(
                    desc_color=desc_color, desc=desc, reset=reset)
            sys.stderr.write(line + '\n')


def emit_markdown(explanation):
    if not explanation:
        return
    try:
        from rich.console import Console
        from rich.markdown import Markdown
    except Exception:
        sys.stderr.write(u'AI:\n{}\n'.format(explanation))
        return

    console = Console(stderr=True)
    console.print('AI:')
    console.print(Markdown(explanation))


def build_corrected_commands(result):
    if not result or not result.commands:
        return []

    def _side_effect(old_cmd, new_cmd):
        emit_ai_result(result)

    if result.streamed:
        side_effect = None
    else:
        side_effect = _side_effect if result.explanation else None
    descriptions = result.descriptions or {}
    corrected = []
    total = len(result.commands)
    for idx, cmd in enumerate(result.commands):
        corrected_command = CorrectedCommand(
            script=cmd,
            side_effect=side_effect,
            priority=const.DEFAULT_PRIORITY * (idx + 1))
        desc = descriptions.get(cmd)
        if desc:
            corrected_command.desc = desc
        corrected_command._tf_source = 'ai'
        corrected_command._tf_index = idx + 1
        corrected_command._tf_total = total
        corrected.append(corrected_command)
    return corrected


def fallback_corrected_commands(command, corrected_commands):
    try:
        first = next(corrected_commands)
    except StopIteration:
        result = get_ai_suggestion(command)
        corrected = build_corrected_commands(result)
        if corrected:
            return iter(corrected), result
        return iter(()), result

    return chain([first], corrected_commands), None


def get_ai_suggestion(command, prompt=None, warn_on_error=False):
    if not is_enabled():
        return

    stream_output = bool(settings.ai_stream_output)
    payload = _build_payload(command, prompt)
    try:
        response_text, streamed = _send_request(
            payload, stream_output=stream_output)
    except Exception as exc:
        if warn_on_error:
            logs.warn(u'AI request failed: {}'.format(exc))
        else:
            logs.debug(u'AI request failed: {}'.format(exc))
        return

    result = _parse_response(response_text, streamed)
    if not result:
        return
    return result


def _build_payload(command, prompt):
    output = six.text_type(command.output or '')
    system_prompt = SYSTEM_PROMPT
    system_prompt += '\n\nLanguage:\n{}'.format(
        _language_instruction(command, prompt))
    user_lines = [
        'Failed command:',
        six.text_type(command.script or ''),
        '',
        'Output:',
        output
    ]
    if prompt:
        user_lines.extend(['', 'User prompt:', six.text_type(prompt)])

    payload = {
        'model': settings.ai_model,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': '\n'.join(user_lines)}
        ],
        'stream': bool(settings.ai_stream)
    }
    if settings.ai_reasoning_effort:
        payload['reasoning'] = {'effort': settings.ai_reasoning_effort}
    return payload


def _send_request(payload, stream_output=False):
    data = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if settings.ai_token:
        headers['Authorization'] = 'Bearer {}'.format(settings.ai_token)
    if settings.ai_stream:
        headers['Accept'] = 'text/event-stream'
    req = request.Request(settings.ai_url, data=data, headers=headers)
    try:
        response = request.urlopen(req, timeout=settings.ai_timeout)
        try:
            if settings.ai_stream:
                content_type = response.headers.get('Content-Type', '')
                if 'text/event-stream' in content_type:
                    return _read_sse_response(
                        response, stream_output=stream_output)
            return response.read().decode('utf-8'), False
        finally:
            response.close()
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError('status {}: {}'.format(exc.code, body))
    except URLError as exc:
        raise RuntimeError(str(exc))


def _read_sse_response(response, stream_output=False):
    chunks = []
    stream_writer = _make_stream_writer() if stream_output else None
    while True:
        line = response.readline()
        if not line:
            break
        if isinstance(line, bytes):
            line = line.decode('utf-8', errors='replace')
        line = line.rstrip('\r\n')
        if not line:
            continue
        if not line.startswith('data:'):
            continue
        data = line[5:]
        if data.startswith(' '):
            data = data[1:]
        data = data.rstrip('\r\n')
        if data == '[DONE]':
            break
        chunk = _extract_stream_chunk(data)
        if chunk:
            chunks.append(chunk)
            if stream_writer:
                stream_writer.feed(chunk)
    streamed = False
    if stream_writer:
        stream_writer.finish()
        streamed = stream_writer.streamed
    return ''.join(chunks), streamed


def _extract_stream_chunk(data):
    try:
        parsed = json.loads(data)
    except ValueError:
        return data

    if isinstance(parsed, dict):
        choices = parsed.get('choices')
        if isinstance(choices, list) and choices:
            choice = choices[0] or {}
            if isinstance(choice, dict):
                delta = choice.get('delta')
                if isinstance(delta, dict) and 'content' in delta:
                    return delta.get('content') or ''
                message = choice.get('message')
                if isinstance(message, dict) and 'content' in message:
                    return message.get('content') or ''
                if 'text' in choice:
                    return choice.get('text') or ''
        if 'content' in parsed:
            return parsed.get('content') or ''

    return ''


class _StreamWriter(object):
    def __init__(self):
        self.streamed = False
        self._buffer = ''
        self._pending = ''
        self._started = False
        self._done = False
        self._text = ''
        self._console = None
        self._live = None
        self._markdown_cls = None
        self._use_rich = False
        self._init_rich()

    def _init_rich(self):
        try:
            from rich.console import Console
            from rich.live import Live
            from rich.markdown import Markdown
        except Exception:
            return
        self._use_rich = True
        self._console = Console(stderr=True, theme=_build_ai_theme())
        self._live = Live(Markdown(''), console=self._console,
                          refresh_per_second=8)
        self._markdown_cls = Markdown

    def feed(self, chunk):
        if self._done:
            return
        self._buffer += chunk
        lower = self._buffer.lower()
        idx = lower.find('answer:')
        if idx != -1:
            out = self._buffer[:idx]
            self._buffer = self._buffer[idx:]
            self._done = True
            self._emit(out, final=True)
            return

        keep = len('answer:') - 1
        if len(self._buffer) > keep:
            out = self._buffer[:-keep]
            self._buffer = self._buffer[-keep:]
            self._emit(out, final=False)

    def finish(self):
        if not self._done and self._buffer:
            self._emit(self._buffer, final=True)
            self._buffer = ''
        if self._use_rich and self._live and self._started:
            self._live.stop()
        elif self._started:
            sys.stderr.write('\n')
            sys.stderr.flush()

    def _emit(self, text, final):
        if not text:
            return
        if not self._started:
            self._pending += text
            if len(self._pending) < 16 and not final:
                return
            text = self._strip_think_prefix(self._pending)
            self._pending = ''
            if not text and not final:
                return
            self._start()
        if self._use_rich:
            self._text += text
            self._live.update(self._markdown_cls(self._text))
        else:
            sys.stderr.write(text)
            sys.stderr.flush()

    def _start(self):
        if self._started:
            return
        self._started = True
        self.streamed = True
        if self._use_rich:
            self._console.print('AI:', style='ai.label')
            self._live.start()
        else:
            sys.stderr.write('{}AI:{} '.format(
                logs.color(colorama.Style.BRIGHT + colorama.Fore.GREEN),
                logs.color(colorama.Style.RESET_ALL)))
            sys.stderr.flush()

    def _strip_think_prefix(self, text):
        stripped = text.lstrip()
        lower = stripped.lower()
        if lower.startswith('think:'):
            stripped = stripped[len('think:'):].lstrip()
        return stripped


def _make_stream_writer():
    return _StreamWriter()


def _parse_response(response_text, streamed):
    try:
        data = json.loads(response_text)
    except ValueError:
        logs.debug(u'AI response is not JSON')
        return _parse_content(response_text, streamed)

    content = _extract_content(data)
    if content is None:
        logs.debug(u'AI response missing content')
        return

    result = _parse_content(content, streamed)
    if not result:
        return
    return result


def _extract_content(data):
    if isinstance(data, dict):
        if 'command' in data or 'commands' in data or 'explanation' in data:
            return data
        choices = data.get('choices')
        if isinstance(choices, list) and choices:
            choice = choices[0] or {}
            if isinstance(choice, dict):
                message = choice.get('message', {})
                if isinstance(message, dict) and 'content' in message:
                    return message.get('content')
                if 'text' in choice:
                    return choice.get('text')
        if 'content' in data:
            return data.get('content')
    return None


def _parse_content(content, streamed):
    if isinstance(content, dict):
        structured = _normalize_structured(content, streamed)
        if structured:
            return structured
        return _normalize_result(content, streamed)

    if not isinstance(content, six.string_types):
        content = six.text_type(content)
    content = content.strip()
    if not content:
        return

    structured = _parse_think_answer(content, streamed)
    if structured:
        return structured

    parsed = _try_parse_json(content)
    if parsed is None:
        commands = _extract_commands_from_markdown(content)
        explanation = _strip_commands_section(content)
        return AiResult(commands=commands,
                        explanation=explanation,
                        streamed=streamed,
                        descriptions={})
    if isinstance(parsed, dict):
        structured = _normalize_structured(parsed, streamed)
        if structured:
            return structured
        return _normalize_result(parsed, streamed)
    return _parse_content(six.text_type(parsed), streamed)


def _try_parse_json(content):
    try:
        return json.loads(content)
    except ValueError:
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1 and end > start:
            snippet = content[start:end + 1]
            try:
                return json.loads(snippet)
            except ValueError:
                return
    return


def _normalize_result(parsed, streamed):
    if not isinstance(parsed, dict):
        return

    commands = parsed.get('commands', parsed.get('command', ''))
    explanation = parsed.get('explanation', '')

    if commands is None:
        commands = ''
    if explanation is None:
        explanation = ''

    commands = _normalize_commands(commands)
    explanation = six.text_type(explanation).strip()

    return AiResult(commands=commands, explanation=explanation, streamed=streamed,
                    descriptions={})


def _normalize_structured(parsed, streamed):
    if not isinstance(parsed, dict):
        return

    if 'think' in parsed and 'answer' in parsed:
        think = parsed.get('think', '')
        answer = parsed.get('answer', {})
        answer_obj = _coerce_json(answer)
        return _build_from_answer(answer_obj, think, streamed)

    if 'primary' in parsed or 'alternatives' in parsed:
        return _build_from_answer(parsed, '', streamed)

    return


def _parse_think_answer(content, streamed):
    match = re.search(r'(?i)answer\s*:\s*', content)
    if not match:
        return

    answer_text = content[match.end():]
    think_text = content[:match.start()]
    think_text = _strip_think_prefix(think_text)
    answer_text = _strip_code_fence(answer_text)
    answer_obj = _try_parse_json(answer_text)
    if not isinstance(answer_obj, dict):
        answer_obj = _extract_json_from_text(answer_text)
    return _build_from_answer(answer_obj, think_text, streamed)


def _strip_think_prefix(text):
    match = re.search(r'(?i)think\s*:\s*', text)
    if match:
        return text[match.end():].strip()
    return text.strip()


def _extract_json_from_text(text):
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except ValueError:
            return
    return


def _coerce_json(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, six.string_types):
        value = _strip_code_fence(value)
        return _try_parse_json(value) or _extract_json_from_text(value) or {}
    return {}


def _build_from_answer(answer_obj, think_text, streamed):
    if not isinstance(answer_obj, dict):
        answer_obj = {}

    if 'primary' not in answer_obj and 'alternatives' not in answer_obj:
        if 'command' in answer_obj or 'desc' in answer_obj:
            answer_obj = {
                'primary': {
                    'command': answer_obj.get('command', ''),
                    'desc': answer_obj.get('desc', '')
                },
                'alternatives': []
            }

    primary = answer_obj.get('primary') or {}
    alternatives = answer_obj.get('alternatives') or []

    commands = []
    descriptions = []
    primary_command = _extract_command(primary)
    if primary_command:
        commands.append(primary_command)
        desc = _extract_desc(primary)
        descriptions.append((primary_command, desc, True))

    for alt in alternatives[:3]:
        alt_command = _extract_command(alt)
        if alt_command and alt_command not in commands:
            commands.append(alt_command)
            desc = _extract_desc(alt)
            descriptions.append((alt_command, desc, False))

    explanation = _format_think_with_commands(think_text, descriptions)
    descriptions_map = {
        cmd: desc for cmd, desc, _ in descriptions if desc
    }
    explanation = think_text.strip()
    return AiResult(commands=commands, explanation=explanation, streamed=streamed,
                    descriptions=descriptions_map)


def _extract_command(item):
    if isinstance(item, dict):
        return _strip_code_fence(six.text_type(item.get('command', '') or '')).strip()
    return _strip_code_fence(six.text_type(item or '')).strip()


def _extract_desc(item):
    if isinstance(item, dict):
        return six.text_type(item.get('desc', '') or '').strip()
    return ''


def _format_think_with_commands(think_text, descriptions):
    parts = []
    if think_text:
        parts.append(think_text.strip())
    if descriptions:
        parts.append('### Commands')
        for cmd, desc, is_primary in descriptions:
            prefix = '- **{}**'.format(cmd) if is_primary else '- {}'.format(cmd)
            if desc:
                parts.append('{} — {}'.format(prefix, desc))
            else:
                parts.append(prefix)
    return '\n'.join(parts).strip()


def _normalize_commands(commands):
    if commands is None:
        return []
    if isinstance(commands, six.string_types):
        return _clean_commands([commands])
    if isinstance(commands, (list, tuple)):
        return _clean_commands(commands)
    return _clean_commands([six.text_type(commands)])


def _clean_commands(commands):
    cleaned = []
    for cmd in commands:
        if cmd is None:
            continue
        cmd_text = _strip_code_fence(six.text_type(cmd)).strip()
        if cmd_text:
            cleaned.append(cmd_text)
    return cleaned


def _extract_commands_from_markdown(content):
    lines = content.splitlines()
    commands = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _is_commands_heading(stripped):
            in_section = True
            continue
        if in_section:
            if stripped.startswith('#'):
                break
            command = _parse_command_line(stripped)
            if command:
                commands.append(command)
            elif commands:
                break
    return commands


def _is_commands_heading(line):
    heading = line.lstrip('#').strip().rstrip(':').lower()
    return heading in (
        'commands', 'command', 'command suggestions', 'suggested commands'
    )


def _parse_command_line(line):
    stripped = line.strip()
    if stripped.startswith(('-', '*', '+')):
        stripped = stripped[1:].strip()
    elif stripped[:2].isdigit() and stripped[1] in ('.', ')'):
        stripped = stripped[2:].strip()
    elif stripped[:3].isdigit() and stripped[2] in ('.', ')'):
        stripped = stripped[3:].strip()
    if stripped.startswith('`') and stripped.endswith('`'):
        stripped = stripped[1:-1].strip()
    return stripped or None


def _strip_commands_section(content):
    lines = content.splitlines()
    output = []
    in_section = False
    for line in lines:
        stripped = line.strip()
        if _is_commands_heading(stripped):
            in_section = True
            continue
        if in_section:
            if stripped.startswith('#') or not stripped:
                in_section = False
            else:
                continue
        if not in_section:
            output.append(line)
    return '\n'.join(output).strip()


def _strip_code_fence(text):
    text = text.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines and lines[0].startswith('```'):
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        return '\n'.join(lines).strip()
    return text

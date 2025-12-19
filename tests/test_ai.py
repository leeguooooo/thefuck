import json

from thefuck import ai
from thefuck.types import Command


def _response_with_content(content):
    return json.dumps({'choices': [{'message': {'content': content}}]})


def test_get_ai_suggestion_parses_json(settings, monkeypatch):
    settings.ai_enabled = True
    settings.ai_url = 'http://example.test'
    settings.ai_model = 'gpt-5.2'

    monkeypatch.setattr(
        ai,
        '_send_request',
        lambda payload, stream_output=False: (
            _response_with_content(
                '{"commands":["git status"],"explanation":"typo"}'),
            False))

    result = ai.get_ai_suggestion(Command('git stauts', 'error'))

    assert result.commands == ['git status']
    assert result.explanation == 'typo'
    assert result.streamed is False


def test_get_ai_suggestion_plain_text(settings, monkeypatch):
    settings.ai_enabled = True
    settings.ai_url = 'http://example.test'
    settings.ai_model = 'gpt-5.2'

    monkeypatch.setattr(
        ai,
        '_send_request',
        lambda payload, stream_output=False: (
            _response_with_content(
                'Explanation text.\n\nCommands:\n- git status\n'),
            False))

    result = ai.get_ai_suggestion(Command('git stauts', 'error'))

    assert result.commands == ['git status']
    assert result.explanation == 'Explanation text.'
    assert result.streamed is False


def test_get_ai_suggestion_think_answer(settings, monkeypatch):
    settings.ai_enabled = True
    settings.ai_url = 'http://example.test'
    settings.ai_model = 'gpt-5.2'

    content = (
        'think: This is **why** it failed.\n'
        'answer: {"primary":{"command":"ls -a","desc":"list all files"},'
        '"alternatives":[{"command":"ls -la","desc":"long list"}]}'
    )
    monkeypatch.setattr(
        ai,
        '_send_request',
        lambda payload, stream_output=False: (
            _response_with_content(content),
            False))

    result = ai.get_ai_suggestion(Command('lsa', 'not found'))

    assert result.commands == ['ls -a', 'ls -la']
    assert 'This is **why** it failed.' in result.explanation
    assert 'Commands' in result.explanation
    assert result.streamed is False

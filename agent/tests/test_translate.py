"""Tests for on-the-fly thought translation."""

from types import SimpleNamespace

import pytest

from superextra_agent import translate
from superextra_agent.gear_run_state import GearRunState


class _FakeModels:
    def __init__(self, text):
        self._text = text
        self.calls = []

    async def generate_content(self, *, model, contents):
        self.calls.append((model, contents))
        return SimpleNamespace(text=self._text)


class _FakeClient:
    def __init__(self, text):
        self.aio = SimpleNamespace(models=_FakeModels(text))


@pytest.mark.asyncio
async def test_skips_empty_and_english_and_missing_target(monkeypatch):
    # Should never touch the model on these paths.
    monkeypatch.setattr(
        translate, "_client", lambda: (_ for _ in ()).throw(AssertionError("called"))
    )
    assert await translate.localize_thought("", "pl") == ""
    assert await translate.localize_thought("hi", None) == "hi"
    assert await translate.localize_thought("hi", "en") == "hi"


@pytest.mark.asyncio
async def test_translates_for_non_english_target(monkeypatch):
    fake = _FakeClient("**Czytam opinie**\n\nPrzeglądam recenzje.")
    monkeypatch.setattr(translate, "_client", lambda: fake)
    out = await translate.localize_thought("**Reading reviews**\n\nReviewing reviews.", "pl")
    assert out == "**Czytam opinie**\n\nPrzeglądam recenzje."
    # The target language name reached the prompt.
    assert "Polish" in fake.aio.models.calls[0][1][0].parts[0].text


@pytest.mark.asyncio
async def test_falls_back_to_original_on_error(monkeypatch):
    class _Boom:
        @property
        def aio(self):
            raise RuntimeError("vertex down")

    monkeypatch.setattr(translate, "_client", lambda: _Boom())
    assert await translate.localize_thought("**Reading**", "de") == "**Reading**"


@pytest.mark.asyncio
async def test_empty_model_reply_keeps_original(monkeypatch):
    monkeypatch.setattr(translate, "_client", lambda: _FakeClient(""))
    assert await translate.localize_thought("**Reading**", "de") == "**Reading**"


def test_run_state_exposes_prompt_language_to_event_mapper():
    state = GearRunState(
        sid="s",
        invocation_id="i",
        run_id="r",
        turn_idx=1,
        user_id="u",
        query_text="q",
        fs=None,
        prompt_language="pl",
    )
    # mapping_state carries it so the safe-thought fallback localizes.
    assert state.mapping_state.get("promptLanguage") == "pl"

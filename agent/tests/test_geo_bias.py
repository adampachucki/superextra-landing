"""Tests for _inject_geo_bias callback."""

from superextra_agent.specialists import _inject_geo_bias
from google.genai import types


class MockCallbackContext:
    def __init__(self, state=None):
        self.state = state or {}


class MockLlmRequest:
    def __init__(self):
        self.config = None


class TestInjectGeoBias:
    def test_sets_retrieval_config_when_coords_present(self):
        ctx = MockCallbackContext(state={"_target_lat": 52.2297, "_target_lng": 21.0122})
        req = MockLlmRequest()

        result = _inject_geo_bias(ctx, req)

        assert result is None
        assert req.config.tool_config.retrieval_config.lat_lng.latitude == 52.2297
        assert req.config.tool_config.retrieval_config.lat_lng.longitude == 21.0122

    def test_noop_when_no_coords(self):
        ctx = MockCallbackContext(state={})
        req = MockLlmRequest()

        result = _inject_geo_bias(ctx, req)

        assert result is None
        assert req.config is None

    def test_preserves_existing_config(self):
        ctx = MockCallbackContext(state={"_target_lat": 52.2297, "_target_lng": 21.0122})
        req = MockLlmRequest()
        req.config = types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
        )

        _inject_geo_bias(ctx, req)

        assert req.config.thinking_config.thinking_level == "HIGH"
        assert req.config.tool_config.retrieval_config.lat_lng.latitude == 52.2297

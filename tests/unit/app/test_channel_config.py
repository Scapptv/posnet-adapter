"""ChannelConfig parsing (AI-2.5 hardening) — typed channels.config, no DB."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.core.app.sync.channel_config import ChannelConfig, parse_channel_config


@pytest.mark.unit
def test_parse_none_yields_defaults() -> None:
    cfg = parse_channel_config(None)
    assert cfg.base_url is None
    assert cfg.webhook_secret is None
    assert cfg.safety_stock == 0


@pytest.mark.unit
def test_parse_dict_typed_and_preserves_extra() -> None:
    cfg = parse_channel_config(
        {"base_url": "http://x", "webhook_secret": "s", "safety_stock": 3, "vendor_key": "v"}
    )
    assert cfg.base_url == "http://x"
    assert cfg.webhook_secret == "s"
    assert cfg.safety_stock == 3
    # extra='allow' keeps adapter-specific keys
    assert cfg.model_extra is not None and cfg.model_extra["vendor_key"] == "v"


@pytest.mark.unit
def test_parse_negative_safety_stock_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_channel_config({"safety_stock": -1})


@pytest.mark.unit
def test_default_config_has_zero_safety_stock() -> None:
    assert ChannelConfig().safety_stock == 0

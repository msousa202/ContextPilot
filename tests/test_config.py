import os
import pytest
from contextpilot.config import ContextPilotConfig


def test_defaults():
    cfg = ContextPilotConfig()
    assert cfg.compression.level == "balanced"
    assert cfg.compression.quality_threshold == 72.0
    assert cfg.compression.history_window == 6
    assert cfg.compression.rag_relevance_min == 0.15
    assert cfg.shadow_testing.enabled is False
    assert cfg.shadow_testing.sample_rate == 0.05
    assert cfg.telemetry.enabled is True


def test_load_from_dict():
    cfg = ContextPilotConfig.model_validate({
        "compression": {"level": "aggressive", "quality_threshold": 70.0},
        "shadow_testing": {"enabled": True, "sample_rate": 0.10},
    })
    assert cfg.compression.level == "aggressive"
    assert cfg.compression.quality_threshold == 70.0
    assert cfg.shadow_testing.enabled is True
    assert cfg.shadow_testing.sample_rate == 0.10


def test_env_var_overrides(monkeypatch):
    monkeypatch.setenv("CONTEXTPILOT_QUALITY_THRESHOLD", "70")
    monkeypatch.setenv("CONTEXTPILOT_COMPRESSION_LEVEL", "conservative")
    monkeypatch.setenv("CONTEXTPILOT_API_KEY", "test-key")
    cfg = ContextPilotConfig.load()
    assert cfg.compression.quality_threshold == 70.0
    assert cfg.compression.level == "conservative"
    assert cfg.telemetry.api_key == "test-key"


def test_load_no_file():
    cfg = ContextPilotConfig.load(path="nonexistent.yaml")
    assert cfg.compression.quality_threshold == 72.0


def test_load_from_yaml_file(tmp_path):
    yaml_file = tmp_path / "contextpilot.yaml"
    yaml_file.write_text(
        "compression:\n  level: conservative\n  history_window: 3\n"
    )
    cfg = ContextPilotConfig.load(path=str(yaml_file))
    assert cfg.compression.level == "conservative"
    assert cfg.compression.history_window == 3

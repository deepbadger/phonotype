
def test_aipp_provider_validation_resets_invalid():
    from phonotype.core.config import AppConfig
    cfg = AppConfig()
    cfg.data["aipp_provider"] = "invalid"
    cfg._validate_aipp_config()
    assert cfg.data["aipp_provider"] in (
        "ollama", "openai", "openrouter", "anthropic", "xai", "gigachat", "openai_compatible"
    )


def test_aipp_models_backfill_for_new_provider():
    """A config that predates a provider (missing or blank entry) should get its
    default model list/selection seeded, not left empty — otherwise the GUI model
    dropdown is blank and unselectable."""
    from phonotype.core.config import AppConfig
    cfg = AppConfig()
    # Simulate an older config.yaml: openrouter absent, plus a stale empty entry.
    cfg.data["aipp_models"].pop("openrouter", None)
    cfg.data["aipp_selected_models"].pop("openrouter", None)
    cfg.data["aipp_models"]["openai"] = []
    cfg.data["aipp_selected_models"]["openai"] = ""
    cfg._validate_aipp_config()
    assert cfg.data["aipp_models"]["openrouter"]            # non-empty list
    assert cfg.data["aipp_selected_models"]["openrouter"]   # a default selection
    assert cfg.data["aipp_models"]["openai"]                # repaired blank list
    assert cfg.data["aipp_selected_models"]["openai"]


def test_removed_features_are_dropped_from_an_old_config():
    """A config written by phonotype 1.x still carries Flux and llama.cpp settings."""
    import yaml
    import phonotype.core.config as C
    old = dict(C.DEFAULT_CONFIG, flux_min_silence_ms=500, llamacpp_server_url="http://localhost:8080",
               aipp_provider="llamacpp_server")
    old["aipp_models"] = dict(old["aipp_models"], llamacpp_server=["m"])
    C.CONFIG_PATH.write_text(yaml.safe_dump(old))
    cfg = C.AppConfig()
    assert not [k for k in cfg.data if k.startswith(("flux_", "llamacpp_"))]
    assert cfg.data["aipp_provider"] == "ollama"
    assert "llamacpp_server" not in cfg.data["aipp_models"]

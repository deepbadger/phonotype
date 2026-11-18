"""Proxy for the cloud AIPP providers (config key aipp_proxy)."""
import pytest


def test_normalize_proxy():
    from phonotype.core.aipp import normalize_proxy as n
    assert n("") == "" and n(None) == ""
    assert n("10.0.0.1:3128") == "http://10.0.0.1:3128"
    assert n("socks5://127.0.0.1:1080") == "socks5h://127.0.0.1:1080"      # DNS through the proxy
    assert n("socks5h://u:p@host:1080/") == "socks5h://u:p@host:1080"
    assert n("socks4://host:1080") == "socks4a://host:1080"
    for bad in ("ftp://host:21", "socks5://host", "http://", "socks5://host:abc"):
        with pytest.raises(ValueError):
            n(bad)


class _Resp:
    ok = True

    def json(self):
        return {"choices": [{"message": {"content": " done "}}]}


def _run(monkeypatch, provider, proxy, **extra):
    import phonotype.core.aipp as A
    from phonotype.core.config import get_config
    calls = []
    monkeypatch.setattr(A.requests, "post", lambda url, **kw: calls.append((url, kw)) or _Resp())
    monkeypatch.setattr(A, "socks_supported", lambda: True)
    cfg = get_config()
    cfg.data.update(aipp_provider=provider, aipp_proxy=proxy, **extra)
    cfg.data["aipp_selected_models"][provider] = "m"
    return A.run_aipp("text", cfg), calls


def test_cloud_request_goes_through_proxy(monkeypatch):
    out, calls = _run(monkeypatch, "openrouter", "socks5://127.0.0.1:1080")
    assert out == "done"
    assert calls[0][1]["proxies"] == {"http": "socks5h://127.0.0.1:1080", "https": "socks5h://127.0.0.1:1080"}


def test_no_proxy_configured_means_no_proxies_argument(monkeypatch):
    _, calls = _run(monkeypatch, "openai", "")
    assert "proxies" not in calls[0][1]


def test_local_endpoints_bypass_the_proxy(monkeypatch):
    _, calls = _run(monkeypatch, "openai_compatible", "http://proxy:3128",
                    aipp_openai_compatible_base_url="http://127.0.0.1:8000/v1",
                    aipp_openai_compatible_api_key="k")
    assert "proxies" not in calls[0][1]
    _, calls = _run(monkeypatch, "openai_compatible", "http://proxy:3128",
                    aipp_openai_compatible_base_url="https://llm.example.com/v1",
                    aipp_openai_compatible_api_key="k")
    assert calls[0][1]["proxies"]["https"] == "http://proxy:3128"


def test_bad_proxy_is_ignored_not_fatal(monkeypatch):
    out, calls = _run(monkeypatch, "openai", "ftp://nope:1")
    assert out == "done" and "proxies" not in calls[0][1]


def test_socks_without_pysocks_leaves_transcript_untouched(monkeypatch):
    import phonotype.core.aipp as A
    from phonotype.core.config import get_config
    monkeypatch.setattr(A, "socks_supported", lambda: False)
    monkeypatch.setattr(A.requests, "post", lambda *a, **k: pytest.fail("must not connect directly"))
    cfg = get_config()
    cfg.data.update(aipp_enabled=True, aipp_provider="openai", aipp_proxy="socks5://h:1080")
    assert A.get_final_text("text", cfg) == "text"


def test_check_connection_reports_route(monkeypatch):
    import phonotype.core.aipp as A
    from phonotype.core.config import get_config
    seen = {}
    monkeypatch.setattr(A, "socks_supported", lambda: True)
    monkeypatch.setattr(A.requests, "get", lambda url, **kw: seen.update(url=url, **kw))
    cfg = get_config()
    cfg.data.update(aipp_provider="openrouter", aipp_proxy="socks5://127.0.0.1:1080")
    ok, msg = A.check_connection(cfg)
    assert ok and "openrouter.ai" in msg and "socks5h proxy 127.0.0.1" in msg
    assert seen["proxies"]["https"] == "socks5h://127.0.0.1:1080"

    def boom(url, **kw):
        raise A.requests.ConnectionError("refused")
    monkeypatch.setattr(A.requests, "get", boom)
    ok, msg = A.check_connection(cfg)
    assert not ok and "refused" in msg
    assert A.check_connection(cfg, "ollama")[0] is False


def test_temperature_comes_from_config(monkeypatch):
    import json
    _, calls = _run(monkeypatch, "openai", "")
    assert json.loads(calls[0][1]["data"])["temperature"] == 0.2
    _, calls = _run(monkeypatch, "openai", "", aipp_temperature=0.6)
    assert json.loads(calls[0][1]["data"])["temperature"] == 0.6


def test_default_prompts_and_legacy_migration():
    import yaml
    from pathlib import Path
    import phonotype.core.config as C
    shipped = yaml.safe_load((Path(C.__file__).parent.parent / "defaults" / "default_config.yaml").read_text())
    assert shipped["aipp_prompts"] == C.DEFAULT_CONFIG["aipp_prompts"]
    assert shipped["aipp_temperature"] == C.DEFAULT_CONFIG["aipp_temperature"] == 0.2
    assert C.DEFAULT_CONFIG["aipp_prompts"]["default"].endswith("---")

    cfg = C.get_config()
    cfg.data["aipp_prompts"] = dict(C.LEGACY_PROMPTS, prompt2="my own prompt", prompt3="")
    cfg._validate_aipp_config()
    assert cfg.data["aipp_prompts"]["default"] == C.PROMPT_CLEAN_REQUEST      # untouched old default → new
    assert cfg.data["aipp_prompts"]["prompt1"] == C.PROMPT_TASK_STATEMENT
    assert cfg.data["aipp_prompts"]["prompt2"] == "my own prompt"             # edited → kept

"""Tray menu layout: grouped, current values in the titles, short model names."""


def test_short_model_name_and_elide():
    from phonotype.tray.tray_main import elide_middle, short_model_name
    assert short_model_name("ggml-large-v3-russian-q5_0.bin") == "large-v3-russian-q5_0"
    assert short_model_name("custom.bin") == "custom"
    assert elide_middle("abcdefghij", 5) == "ab…ij"
    assert len(short_model_name("ggml-" + "x" * 80 + ".bin", 30)) == 30
    assert elide_middle("", 10) == "" and elide_middle(None, 10) == ""


def _labels(menu):
    return ["---" if a.isSeparator() else a.text().rstrip("\u00a0") for a in menu.actions()]


def test_menu_structure_follows_config(qapp, monkeypatch, tmp_path):
    import phonotype.models as M
    cache = tmp_path / "cache"; cache.mkdir()
    monkeypatch.setattr(M, "CACHE_DIR", cache)
    monkeypatch.setattr(M, "REPO_MODELS", tmp_path / "repo")
    whisper = cache / "ggml-large-v3-russian-q5_0.bin"; whisper.write_bytes(b"x")
    parakeet = cache / "ggml-parakeet-tdt-0.6b-v3-q8_0.bin"; parakeet.write_bytes(b"x")

    from phonotype.core.config import get_config
    cfg = get_config()
    monkeypatch.setattr(cfg, "save", lambda: None)
    cfg.data.update(asr_engine="whisper", whisper_model_path=str(whisper),
                    parakeet_model_path=str(parakeet), language="ru", aipp_enabled=False)

    import phonotype.tray.tray_main as T
    tray = T.PhonotypeTrayApp()
    assert _labels(tray.menu) == [
        "Start Recording", "Paste Last Dictation", "---",
        "Model: large-v3-russian-q5_0", "Language: Russian…", "AI Processing: Off", "---",
        "History…", "Performance…", "Settings…", "---",
        "Quit"]

    # Parakeet detects the language itself → no Language item; AI state shows the model
    cfg.data.update(asr_engine="parakeet", aipp_enabled=True, aipp_provider="openai")
    cfg.data["aipp_selected_models"] = {"openai": "gpt-x"}
    tray.refresh_tray_menu()
    labels = _labels(tray.menu)
    assert "Model: parakeet-tdt-0.6b-v3-q8_0" in labels
    assert not any(l.startswith("Language") for l in labels)
    assert "AI Processing: gpt-x" in labels

    # AI submenu is flat: on/off, the four prompts, what is used, one link to settings
    ai = next(a.menu() for a in tray.menu.actions() if a.text().startswith("AI Processing"))
    sub = _labels(ai)
    assert sub[0] == "Enabled" and not any(a.menu() for a in ai.actions())
    assert [l.split(":")[0].split(" (")[0] for l in sub[2:6]] == ["Default", "Prompt 1", "Prompt 2", "Prompt 3"]
    assert sub[-2:] == ["openai · gpt-x", "Provider, model, prompts…"]
    ai.actions()[3].trigger()
    assert cfg.data["aipp_active_prompt"] == "prompt1"


def test_submenu_titles_leave_room_for_arrow(qapp):
    from phonotype.tray.tray_main import submenu_title
    assert submenu_title("Model: x").startswith("Model: x")
    assert submenu_title("Model: x").endswith("\u00a0" * 4)


def test_cancel_and_paste_last_follow_state(qapp, tmp_path, monkeypatch):
    from phonotype.core.config import get_config
    monkeypatch.setattr(get_config(), "save", lambda: None)
    import phonotype.tray.tray_main as T
    tray = T.PhonotypeTrayApp()
    assert not tray.paste_last_action.isEnabled()          # nothing dictated yet

    tray.on_transcript_ready("hello")
    assert tray.paste_last_action.isEnabled()

    class _Thread:
        cancelled = False
        def isRunning(self): return True
        def cancel_recording(self): self.cancelled = True

    tray.thread = _Thread()
    tray.set_status("Recording")
    labels = [a.text() for a in tray.menu.actions() if not a.isSeparator()]
    assert labels[:3] == ["Stop Recording", "Cancel Recording", "Paste Last Dictation"]
    assert not tray.paste_last_action.isEnabled()          # not while recording
    tray.cancel_recording()
    assert tray.thread.cancelled

from phonotype.core import vocabulary as V


def test_text_round_trip_and_normalisation():
    entries = V.parse_text("Kubernetes: кубернетес, Кубернетис,кубернетес\n\n# note\nydotool\nkubernetes: x\n")
    assert entries == [
        {"term": "Kubernetes", "sounds_like": ["кубернетес", "Кубернетис"]},
        {"term": "ydotool", "sounds_like": []},
    ]
    assert V.to_text(entries) == "Kubernetes: кубернетес, Кубернетис\nydotool"
    assert V.normalize(["Qt", {"term": ""}, 5, {"term": "Qt"}]) == [{"term": "Qt", "sounds_like": []}]


def test_apply_replaces_whole_words_only():
    entries = V.parse_text("Kubernetes: кубернетес\nPhonotype: фонотайп, фоно тайп\nydotool")
    text = "Запусти Кубернетес, потом фоно тайп и YDOTOOL. Некубернетес не трогай."
    assert V.apply(text, entries) == (
        "Запусти Kubernetes, потом Phonotype и ydotool. Некубернетес не трогай.")
    assert V.apply("ничего", []) == "ничего"


def test_whisper_prompt_respects_budget():
    entries = V.normalize([{"term": f"term{i:03d}"} for i in range(200)])
    hint = V.whisper_prompt(entries)
    assert hint.startswith("term000, term001") and len(hint) <= V.WHISPER_PROMPT_CHARS


def test_prompt_note_lists_terms():
    note = V.prompt_note(V.parse_text("Kubernetes: кубернетес\nQt"))
    assert "- Kubernetes (may be heard as: кубернетес)" in note and "- Qt" in note
    assert V.prompt_note([]) == ""


def test_aipp_prompt_keeps_separator_before_transcript(monkeypatch):
    from phonotype.core import aipp
    from phonotype.core.config import get_config
    cfg = get_config()
    cfg.data.update(aipp_provider="ollama", vocabulary=V.parse_text("Kubernetes: кубернетес"),
                    aipp_prompts={"default": "Rewrite.\n---"}, aipp_active_prompt="default")
    seen = {}
    monkeypatch.setattr(aipp, "run_ollama_aipp", lambda prompt, model: seen.setdefault("p", prompt) or "ok")
    try:
        aipp.run_aipp("привет кубернетес", cfg, "default")
    finally:
        cfg.data["vocabulary"] = []
    assert seen["p"].startswith("Vocabulary.") and seen["p"].endswith("Rewrite.\n---\nпривет кубернетес")


def test_transcript_gets_vocabulary_and_whisper_gets_hint(tmp_path, monkeypatch):
    from phonotype.core.config import get_config
    from phonotype.core.transcriber import WhisperTranscriber
    cfg = get_config()
    cfg.data["vocabulary"] = V.parse_text("World: world")
    cfg.data["asr_prewarm"] = False
    cli = tmp_path / "cli"; cli.write_text("#!/bin/sh\n"); cli.chmod(0o755)
    model = tmp_path / "ggml-x.bin"; model.write_text("m")
    wav = tmp_path / "a.wav"; wav.write_bytes(b"RIFF")
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        out = cmd[cmd.index("-of") + 1] + ".txt"
        open(out, "w").write("hello world\n")
        return type("CP", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("phonotype.core.transcriber.subprocess.run", run)
    try:
        t = WhisperTranscriber(str(model), str(cli), delete_input=False, engine="whisper",
                               gpu_enabled=False, vram_check=False, flash_attn=False,
                               filter_hallucinations=False, hallucination_blocklist=[])
        text, _ = t.transcribe(wav)
    finally:
        cfg.data["vocabulary"] = []
        cfg.data["asr_prewarm"] = True
    assert text == "hello World"
    assert seen["cmd"][seen["cmd"].index("--prompt") + 1] == "World"

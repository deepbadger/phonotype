import pytest


def test_timings_summary_has_load_and_total():
    from phonotype.core.transcriber import _extract_whisper_timings
    err = ("parakeet_print_timings:     load time =   869.57 ms\n"
           "parakeet_print_timings:   encode time =   113.54 ms /     1 runs\n"
           "parakeet_print_timings:    total time =  1015.06 ms\n")
    assert _extract_whisper_timings(err) == "load 870 ms, total 1015 ms"
    assert _extract_whisper_timings("no timings here") is None


# ── warm start ──────────────────────────────────────────────────────────────

_FAKE_CLI = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
prefix = args[args.index("-of") + 1]
if args[args.index("-f") + 1] != "-" or "--fail" in open(args[args.index("-m") + 1]).read():
    sys.exit(3)
data = sys.stdin.buffer.read()
open(prefix + ".txt", "w").write("[00:00.000] got %d bytes\\n" % len(data))
sys.stderr.write("fake_print_timings:     load time =   500.00 ms\\n")
"""


def _warm_transcriber(tmp_path, model_text="model"):
    from phonotype.core.transcriber import WhisperTranscriber
    cli = tmp_path / "fake-cli"
    cli.write_text(_FAKE_CLI)
    cli.chmod(0o755)
    model = tmp_path / "ggml-fake.bin"
    model.write_text(model_text)
    wav = tmp_path / "rec.wav"
    wav.write_bytes(b"RIFF" + b"\0" * 96)
    t = WhisperTranscriber(str(model), str(cli), delete_input=False, engine="whisper",
                           gpu_enabled=False, vram_check=False, flash_attn=False,
                           filter_hallucinations=False, hallucination_blocklist=[])
    return t, wav


def test_prewarm_feeds_audio_through_stdin(tmp_path, monkeypatch):
    t, wav = _warm_transcriber(tmp_path)
    assert t.prewarm() is True
    monkeypatch.setattr("phonotype.core.transcriber.subprocess.run",
                        lambda *a, **k: pytest.fail("cold run must not happen"))
    text, _ = t.transcribe(wav)
    assert "got 100 bytes" in text
    assert t._warm is None


def test_prewarm_failure_falls_back_to_normal_run(tmp_path, fake_whisper_run):
    t, wav = _warm_transcriber(tmp_path, model_text="--fail")
    assert t.prewarm() is True
    text, _ = t.transcribe(wav)
    assert "Hello world" in text          # produced by the patched normal run


def test_cancel_prewarm_stops_the_process(tmp_path):
    t, _ = _warm_transcriber(tmp_path)
    assert t.prewarm() is True
    proc = t._warm["proc"]
    t.cancel_prewarm()
    assert proc.poll() is not None and t._warm is None


def test_prewarm_can_be_switched_off(tmp_path):
    from phonotype.core.config import get_config
    t, _ = _warm_transcriber(tmp_path)
    get_config().data["asr_prewarm"] = False
    try:
        assert t.prewarm() is False and t._warm is None
    finally:
        get_config().data["asr_prewarm"] = True

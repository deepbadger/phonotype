"""CoreProcessThread (GUI/tray pipeline) must honour save_recordings like the CLI."""
import pytest


class _FakeRecorder:
    last = None

    def __init__(self, *a, **kw):
        _FakeRecorder.last = self
        self.preserve = None

    def start_recording(self):
        pass

    def stop_recording(self, preserve=False):
        self.preserve = preserve
        return "/tmp/fake.wav"


class _FakeTranscriber:
    last = None

    def __init__(self, *a, delete_input=True, **kw):
        _FakeTranscriber.last = self
        self.delete_input = delete_input
        self.last_gpu_note = None

    def prewarm(self):
        self.prewarmed = True
        return True

    def cancel_prewarm(self):
        self.prewarmed = False

    def transcribe(self, path):
        return "", None  # empty transcript → run() returns right after transcription


class _Cfg:
    def __init__(self, save):
        self.data = {"save_recordings": save}
        self.whisper_model_path = "m.bin"
        self.whisper_binary = "whisper-cli"
        self.language = "ru"
        self.typing_delay = 0
        self.typing_start_delay = 0


@pytest.mark.parametrize("save", [True, False])
def test_core_thread_honours_save_recordings(monkeypatch, save):
    # imported here: conftest stubs sounddevice only once the test is running
    import phonotype.core.recorder as recorder_mod
    import phonotype.core.app_core as app_core

    monkeypatch.setattr(recorder_mod, "AudioRecorder", _FakeRecorder)
    monkeypatch.setattr(app_core, "WhisperTranscriber", _FakeTranscriber)
    monkeypatch.setattr("phonotype.core.typer.SimulatedTyper", lambda *a, **kw: object())
    monkeypatch.setattr("phonotype.core.clipboard.ClipboardManager", lambda *a, **kw: object())

    t = app_core.CoreProcessThread(_Cfg(save), logger=None)
    t.should_stop = True
    t.run()  # synchronously, no Qt event loop needed

    assert _FakeRecorder.last.preserve is save
    assert _FakeTranscriber.last.delete_input is (not save)

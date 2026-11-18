import sys


def test_main_routes_cli(monkeypatch):
    import phonotype.cli.cli_main as cli_mod
    called = {"cli": False}
    monkeypatch.setattr(cli_mod, "main", lambda: called.__setitem__("cli", True))
    # Default invocation with no flags should route to CLI mode
    monkeypatch.setattr(sys, "argv", ["phonotype"])  # default to CLI

    import importlib
    import phonotype.__main__ as main_mod
    importlib.reload(main_mod)  # ensure fresh parse
    main_mod.main()
    assert called["cli"] is True




def test_setup_report_names_what_is_missing(monkeypatch, tmp_path):
    """--setup only reports: no downloads, no sudo, no service edits."""
    import phonotype.models as M
    import phonotype.paths as P
    import phonotype.utils.setup_user as SU
    from phonotype.core.config import get_config

    def missing():
        raise FileNotFoundError("nope")

    monkeypatch.setattr(P, "whisper_cli", missing)
    monkeypatch.setattr(P, "find_parakeet_cli", missing)
    monkeypatch.setattr(M, "installed_models", lambda: [])
    monkeypatch.setattr(SU.shutil, "which", lambda name: None)
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    cfg = get_config()
    cfg.data["asr_engine"] = "whisper"

    report = dict((msg.split(":")[0], ok) for ok, msg in SU.readiness_report(cfg))
    assert report["whisper-cli"] is False          # needed by the active engine
    assert report["parakeet-cli"] is True          # not needed → not an error
    assert report["speech models"] is False
    assert report["ydotool"] is False and report["clipboard tool"] is False
    assert not hasattr(SU, "_ensure_ydotool_prebuilt")

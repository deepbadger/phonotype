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



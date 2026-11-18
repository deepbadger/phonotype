"""Per-user setup (`phonotype --setup`): config, launcher, and a readiness report.

It changes nothing outside the user's own config and launcher files: no sudo,
no downloads, no edits to shell profiles or services. What is missing is
reported with the command that fixes it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from phonotype.core.config import AppConfig


def _ensure_dir(p: Path) -> None:
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _install_desktop_launchers() -> None:
    # Copy icon
    try:
        try:
            from importlib.resources import files
        except Exception:
            from importlib_resources import files  # type: ignore
        icon_src = files("phonotype").joinpath("assets", "phonotype-0.png")
        icon_bytes = icon_src.read_bytes()  # type: ignore[attr-defined]
        icon_dir_256 = Path.home() / ".local/share/icons/hicolor/256x256/apps"
        icon_dir_64 = Path.home() / ".local/share/icons/hicolor/64x64/apps"
        _ensure_dir(icon_dir_256)
        _ensure_dir(icon_dir_64)
        (icon_dir_256 / "phonotype.png").write_bytes(icon_bytes)
        (icon_dir_64 / "phonotype.png").write_bytes(icon_bytes)
    except Exception:
        pass

    # Desktop entries
    apps_dir = Path.home() / ".local/share/applications"
    _ensure_dir(apps_dir)

    def write_desktop(mode: str, name: str) -> None:
        path = apps_dir / f"phonotype-{mode}.desktop"
        try:
            path.write_text(
                (
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    f"Name=Phonotype ({name})\n"
                    f"Exec=phonotype --{mode}\n"
                    "Icon=phonotype\n"
                    "Terminal=false\n"
                    "Categories=Utility;AudioVideo;\n"
                )
            )
        except Exception:
            pass

    write_desktop("tray", "tray")

    # Update caches best-effort
    try:
        subprocess.run(["update-desktop-database", str(apps_dir)], timeout=10, check=False)
    except Exception:
        pass
    try:
        subprocess.run(["gtk-update-icon-cache", str(Path.home() / ".local/share/icons/hicolor")], timeout=10, check=False)
    except Exception:
        pass


def _in_input_group() -> bool | None:
    """True/False, or None when there is no 'input' group."""
    try:
        import grp
        gid = grp.getgrnam("input").gr_gid
    except KeyError:
        return None
    return gid in os.getgroups()


def readiness_report(cfg) -> list[tuple[bool, str]]:
    """(ok, message) lines describing what Phonotype needs to work."""
    from phonotype import models as mdl
    from phonotype import paths

    lines: list[tuple[bool, str]] = []

    def binary(name: str, find, needed: bool):
        try:
            lines.append((True, f"{name}: {find()}"))
        except FileNotFoundError:
            lines.append((not needed, f"{name}: not found — build it with ./setup.sh from the repository"))

    engine = str(cfg.data.get("asr_engine", "whisper")).lower()
    binary("whisper-cli", paths.whisper_cli, engine == "whisper")
    binary("parakeet-cli", paths.find_parakeet_cli, engine == "parakeet")

    installed = mdl.installed_models()
    if installed:
        lines.append((True, f"speech models: {len(installed)} installed"))
    else:
        lines.append((False, "speech models: none — download one in Settings → Models "
                             "or with 'phonotype-model install <key>'"))

    if os.environ.get("XDG_SESSION_TYPE", "").startswith("wayland"):
        ok = bool(shutil.which("ydotool") and shutil.which("ydotoold"))
        lines.append((ok, "ydotool: installed" if ok else "ydotool: not found — install x11-misc/ydotool"))
        member = _in_input_group()
        if member is False:
            lines.append((False, "group 'input': you are not a member — run "
                                 "'gpasswd -a $USER input' as root and log in again"))
        elif member:
            lines.append((True, "group 'input': member"))
    else:
        ok = bool(shutil.which("xdotool"))
        lines.append((ok, "xdotool: installed" if ok else "xdotool: not found — install x11-misc/xdotool"))

    clip = next((t for t in ("wl-copy", "xclip", "xsel") if shutil.which(t)), None)
    lines.append((bool(clip), f"clipboard tool: {clip}" if clip else
                  "clipboard tool: none — install gui-apps/wl-clipboard or x11-misc/xclip"))
    return lines


def run_user_setup(verbose: bool = False) -> None:
    cfg = AppConfig()            # creates the config (and imports VOXD's on first run)
    _install_desktop_launchers()
    try:
        cfg.save()               # persist resolved binary/model paths
    except Exception:
        pass
    for ok, message in readiness_report(cfg):
        print(f"[setup] {'ok ' if ok else '!! '} {message}")

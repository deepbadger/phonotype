import sys
import argparse
import subprocess
import os
from pathlib import Path
if sys.version_info < (3, 12):
    print("[phonotype] Python 3.12 or newer is required.")
    sys.exit(1)
from phonotype.core.config import AppConfig

from phonotype.paths import CONFIG_FILE, resource_path
from phonotype.utils.libw import ORANGE, RESET
import shutil, yaml
import importlib.metadata

def _print_boxed(msg: str):
    """Print a single-line message inside a neat Unicode box.
    Supports ANSI-colored text by ignoring escape codes for width calc.
    """
    import re
    ansi = re.compile(r"\x1b\[[0-9;]*m")
    inner = f" {msg} "
    visible_len = len(ansi.sub('', inner))
    top = "┌" + "─" * visible_len + "┐"
    mid = "│" + inner + "│"
    bot = "└" + "─" * visible_len + "┘"
    print(top)
    print(mid)
    print(bot)

def ensure_user_config() -> dict:
    if not CONFIG_FILE.exists():
        default_tpl = resource_path("defaults/config.yaml")
        shutil.copy(default_tpl, CONFIG_FILE)
    return yaml.safe_load(CONFIG_FILE.read_text())

def _mic_autoset_if_enabled(cfg):
    """Best-effort: unmute default mic and set input gain to configured level.

    Uses wpctl → pactl → amixer if available. Silently skips on failure.
    """
    try:
        debug = bool(cfg.data.get("verbosity", False)) or bool(os.environ.get("PHONOTYPE_DEBUG_AUDIO"))
        def log(msg: str):
            if debug:
                print(f"[mic] {msg}")

        if not cfg.data.get("mic_autoset_enabled", False):
            log("autoset disabled; skipping")
            return
        try:
            level = float(cfg.data.get("mic_autoset_level", 0.40))
        except Exception:
            level = 0.40
        level = max(0.0, min(1.0, level))
        log(f"autoset enabled; target level={level:.2f}")

        def have(cmd: str) -> bool:
            found = shutil.which(cmd) is not None
            log(f"tool '{cmd}': {'found' if found else 'missing'}")
            return found

        # Prefer PipeWire's wpctl if present
        if have("wpctl"):
            try:
                log("trying wpctl … unmute")
                cp1 = subprocess.run(["wpctl", "set-mute", "@DEFAULT_SOURCE@", "0"],
                                     check=False, capture_output=True, timeout=2)
                log(f"wpctl set-mute rc={cp1.returncode}")
                log("trying wpctl … set-volume")
                cp2 = subprocess.run(["wpctl", "set-volume", "@DEFAULT_SOURCE@", f"{level:.2f}"],
                                     check=False, capture_output=True, timeout=2)
                log(f"wpctl set-volume rc={cp2.returncode}")
                return
            except Exception as e:
                log(f"wpctl path failed: {e}")

        # Fallback to PulseAudio pactl (also works on PipeWire's pulse shim)
        if have("pactl"):
            try:
                pct = str(int(round(level * 100))) + "%"
                log("trying pactl … unmute")
                cp1 = subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"],
                                     check=False, capture_output=True, timeout=2)
                log(f"pactl set-source-mute rc={cp1.returncode}")
                log(f"trying pactl … set-volume {pct}")
                cp2 = subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", pct],
                                     check=False, capture_output=True, timeout=2)
                log(f"pactl set-source-volume rc={cp2.returncode}")
                return
            except Exception as e:
                log(f"pactl path failed: {e}")

        # Last resort: ALSA amixer (control names vary by card)
        if have("amixer"):
            try:
                pct = str(int(round(level * 100))) + "%"
                for ctl in ("Capture", "Mic"):
                    log(f"trying amixer on control '{ctl}' … {pct} unmute")
                    r = subprocess.run(["amixer", "-q", "set", ctl, pct, "unmute"],
                                       capture_output=True, timeout=2)
                    log(f"amixer rc={r.returncode}")
                    if r.returncode == 0:
                        return
            except Exception as e:
                log(f"amixer path failed: {e}")
        log("no suitable backend succeeded; leaving mic unchanged")
    except Exception as e:
        # absolutely no-op on any unexpected error
        try:
            if bool(os.environ.get("PHONOTYPE_DEBUG_AUDIO")):
                print(f"[mic] unexpected error: {e}")
        except Exception:
            pass
        return

def _get_version() -> str:
    """Version from the package metadata, else from pyproject.toml."""
    try:
        return importlib.metadata.version("phonotype")
    except Exception:
        # Not installed as a package (source checkout or /opt install): read pyproject.toml
        try:
            from pathlib import Path
            import re
            candidates = [
                Path("/opt/phonotype/pyproject.toml"),
                Path(__file__).parents[2] / "pyproject.toml",
            ]
            for pyproject_path in candidates:
                if pyproject_path.exists():
                    content = pyproject_path.read_text()
                    match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
                    if match:
                        return match.group(1)
        except Exception:
            pass
        
        return "unknown"

def _parse_bool(s: str) -> bool:
    v = (s or "").strip().lower()
    if v in {"1", "true", "on", "yes", "y"}:
        return True
    if v in {"0", "false", "off", "no", "n"}:
        return False
    raise ValueError(f"expected true/false, got: {s}")

def _systemd_user_available() -> bool:
    try:
        # Fast probe; returns 0 and prints version if systemd is available for user
        r = subprocess.run(["systemctl", "--user", "--version"], capture_output=True)
        return r.returncode == 0
    except Exception:
        return False

def _ensure_phonotype_tray_unit() -> None:
    """Ensure a phonotype-tray.service user unit exists (packaged or per-user fallback)."""
    try:
        pkg_unit = Path("/usr/lib/systemd/user/phonotype-tray.service")
        if pkg_unit.exists():
            return
        user_dir = Path.home() / ".config/systemd/user"
        try:
            user_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        unit_path = user_dir / "phonotype-tray.service"
        if not unit_path.exists():
            unit_path.write_text(
                "[Unit]\n"
                "Description=Phonotype tray mode (user)\n"
                "After=default.target\n\n"
                "[Service]\n"
                "Type=simple\n"
                "ExecStart=/usr/bin/phonotype --tray\n"
                "Restart=on-failure\n"
                "RestartSec=2s\n"
                "Environment=YDOTOOL_SOCKET=%h/.ydotool_socket\n\n"
                "[Install]\n"
                "WantedBy=default.target\n"
            )
    except Exception:
        pass

def _xdg_autostart_path() -> Path:
    return Path.home() / ".config" / "autostart" / "phonotype-tray.desktop"

def _ensure_xdg_entry() -> bool:
    try:
        p = _xdg_autostart_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if not p.exists():
            p.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Phonotype (tray)\n"
                "Exec=phonotype --tray\n"
                "X-GNOME-Autostart-enabled=true\n"
                "Hidden=false\n"
            )
        return True
    except Exception:
        return False

def _remove_xdg_entry() -> bool:
    try:
        p = _xdg_autostart_path()
        if p.exists():
            p.unlink()
        return True
    except Exception:
        return False

def _handle_autostart(arg_value: str) -> int:
    """Set autostart true/false; idempotently enable/disable user service or XDG fallback and report status."""
    desired = _parse_bool(arg_value)
    # Persist to config
    cfg = AppConfig()
    cfg.data["autostart"] = desired
    try:
        setattr(cfg, "autostart", desired)
    except Exception:
        pass
    try:
        cfg.save()
    except Exception:
        pass

    used_systemd = False
    enabled = False
    active = False

    # Try systemd --user first
    if _systemd_user_available():
        used_systemd = True
        _ensure_phonotype_tray_unit()
        try:
            subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
        except Exception:
            pass

        def _is_enabled() -> bool:
            try:
                r = subprocess.run(["systemctl", "--user", "is-enabled", "phonotype-tray.service"],
                                   check=False, capture_output=True)
                return r.returncode == 0
            except Exception:
                return False

        def _is_active() -> bool:
            try:
                r = subprocess.run(["systemctl", "--user", "is-active", "phonotype-tray.service"],
                                   check=False, capture_output=True)
                return r.returncode == 0
            except Exception:
                return False

        if desired:
            subprocess.run(["systemctl", "--user", "enable", "--now", "phonotype-tray.service"], check=False)
        else:
            subprocess.run(["systemctl", "--user", "disable", "--now", "phonotype-tray.service"], check=False)

        enabled = _is_enabled()
        active = _is_active()

        # If enabling failed in a way that suggests no user bus, fall back to XDG
        if desired and not (enabled or active):
            used_systemd = False

    # XDG fallback
    if not used_systemd:
        if desired:
            xdg_ok = _ensure_xdg_entry()
            print(f"[autostart] enabled (xdg={xdg_ok})")
            return 0 if xdg_ok else 1
        else:
            xdg_ok = _remove_xdg_entry()
            print(f"[autostart] disabled (xdg={xdg_ok})")
            return 0 if xdg_ok else 1

    # Systemd path: concise status
    if desired:
        print(f"[autostart] enabled (enabled={enabled}, active={active})")
    else:
        print(f"[autostart] disabled (enabled={enabled}, active={active})")
    return 0

def main():
    parser = argparse.ArgumentParser(description="Phonotype App Entry Point", add_help=False)
    # NOTE: we intentionally disable the automatic -h/--help. Sub-mode parsers
    # (and the CLI quick-actions parser) should receive -h/--help when relevant.
    # We render top-level help manually only when no sub-mode or quick-action is
    # present and -h/--help is provided.
    # Mutually-exclusive launch mode flags (simpler UX)
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--tray", action="store_true", help="Launch Phonotype tray-only mode (background)")
    parser.add_argument(
        "--setup",
        action="store_true",
        help="Create the config and launcher, report what is missing, and exit",
    )
    parser.add_argument(
        "--setup-verbose",
        action="store_true",
        help="Run per-user setup with detailed diagnostics and exit",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit"
    )
    parser.add_argument(
        "--autostart",
        metavar="BOOL",
        help="Enable or disable Phonotype user autostart (tray on login): true|false"
    )
    parser.add_argument(
        "--trigger-record",
        action="store_true",
        help="(Internal) signal the running Phonotype App to start recording - use for system-wide HOTKEY setup"
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Print configuration and hotkey status"
    )
    parser.add_argument(
        "-l",
        "--lang",
        dest="lang",
        help="Transcription language (ISO 639-1, e.g. 'en', 'sv', or 'auto' for detection)"
    )
    args, unknown = parser.parse_known_args()

    if args.version:
        print(_get_version())
        sys.exit(0)

    if args.autostart is not None:
        try:
            rc = _handle_autostart(args.autostart)
            sys.exit(rc)
        except Exception as e:
            print(f"[autostart] error: {e}")
            sys.exit(1)

    if args.setup or args.setup_verbose:
        try:
            if args.setup_verbose:
                print("[setup] --setup-verbose is deprecated; --setup now prints detailed diagnostics by default.")
            from phonotype.utils.setup_user import run_user_setup
            run_user_setup(verbose=True)
            print("[setup] Per-user setup complete.")
        except Exception as e:
            print(f"[setup] Per-user setup encountered issues: {e}")
        sys.exit(0)

    # Recognize CLI quick-action flags at top-level to implicitly enter CLI mode
    cli_flags = {
        "--save-audio", "--record", "--rh", "--transcribe", "--log", "--cfg",
        "--aipp", "--no-aipp", "--aipp-prompt", "--aipp-provider", "--aipp-model",
    }
    unknown_flags = {u.split("=")[0] for u in unknown if u.startswith("-")}

    # ------------------------------------------------------------
    #         Top-level help handling (only when no sub-mode or QA)
    # ------------------------------------------------------------
    if not args.tray and not (unknown_flags & cli_flags):
        if "-h" in unknown or "--help" in unknown:
            parser.print_help()
            # Show installed version
            try:
                print(f"\nPhonotype version: {_get_version()}")
            except Exception:
                pass
            # Also show CLI quick actions help for convenience
            try:
                from phonotype.cli.cli_main import build_parser as _build_cli_parser
                print("\n[CLI quick actions] You can use these directly; they run in CLI mode:\n")
                print(_build_cli_parser().format_help())
            except Exception:
                pass
            # Autostart hint
            try:
                print("\n[Autostart] Enable Phonotype tray on login: phonotype --autostart true")
            except Exception:
                pass
            sys.exit(0)


    # If we're just the hotkey sender, dispatch and exit immediately
    if args.trigger_record:
        from phonotype.utils.ipc_client import send_trigger
        send_trigger()
        sys.exit(0)

    cfg = AppConfig()
    # Session-only override for language
    if args.lang:
        try:
            from phonotype.utils.languages import normalize_lang_code, is_valid_lang
            code = normalize_lang_code(args.lang)
            if not is_valid_lang(code):
                print(f"[phonotype] Invalid language '{args.lang}'. Expected ISO 639-1 or 'auto'.")
                sys.exit(2)
            cfg.data["language"] = code
            setattr(cfg, "language", code)
        except Exception as e:
            print(f"[phonotype] Failed to apply language override: {e}")
            sys.exit(2)
    mode = "tray" if args.tray else "cli"

    if args.diagnose:
        print(f"[Diagnose] Current mode: {mode}")
        
        # ydotool daemon on Wayland (checked by process, so any init system works)
        if os.environ.get("XDG_SESSION_TYPE") == "wayland":
            if shutil.which("ydotool"):
                try:
                    running = subprocess.run(["pgrep", "-x", "ydotoold"],
                                             capture_output=True, timeout=3).returncode == 0
                    if running:
                        print("[Diagnose] ydotool daemon: ✅ running")
                    else:
                        print("[Diagnose] ydotool daemon: ❌ not running")
                        print("[Diagnose] → Fix: rc-service --user phonotype-ydotoold start "
                              "(systemd: systemctl --user start ydotoold.service)")
                except Exception:
                    print("[Diagnose] ydotool daemon: ❌ cannot check status")
            else:
                print("[Diagnose] ydotool: ❌ not installed")

        # What is missing to work at all (binaries, model, typing and clipboard tools)
        try:
            from phonotype.utils.setup_user import readiness_report
            for ok, message in readiness_report(cfg):
                print(f"[Diagnose] {'✅' if ok else '❌'} {message}")
        except Exception as e:
            print(f"[Diagnose] readiness check failed: {e}")

        # Audio device diagnostics
        try:
            import sounddevice as sd
            print("[Diagnose] sounddevice default:", sd.default.device)
            try:
                inp = sd.query_devices(kind='input')
                print(f"[Diagnose] default input: {inp.get('name')} @ {inp.get('default_samplerate')} Hz")
            except Exception:
                pass
            # Enumerate devices
            try:
                devs = sd.query_devices()
                print("[Diagnose] Available devices:")
                for i, d in enumerate(devs):
                    name = d.get('name', 'unknown')
                    mi = d.get('max_input_channels', 0)
                    sr = d.get('default_samplerate', None)
                    print(f"  [{i}] {name} | in={mi} | default_sr={sr}")
                # Pulse hint
                names = [str(d.get('name','')).lower() for d in devs]
                has_pulse = any('pulse' in n for n in names)
                if not has_pulse:
                    print("[Diagnose] Hint: No 'pulse' device detected.")
                    print("  Install the ALSA plugin of your sound server (PipeWire: media-video/pipewire[sound-server], "
                          "media-plugins/alsa-plugins[pulseaudio]).")
            except Exception:
                pass
        except Exception:
            print("[Diagnose] sounddevice not available")

        # ASR engine (whisper | parakeet)
        engine = str(cfg.data.get("asr_engine", "whisper"))
        print(f"[Diagnose] config asr_engine: {engine}")
        if engine == "parakeet":
            from phonotype.paths import find_parakeet_cli, find_parakeet_model
            for label, key, finder in (("parakeet-cli", "parakeet_binary", find_parakeet_cli),
                                       ("parakeet model", "parakeet_model_path", find_parakeet_model)):
                try:
                    print(f"[Diagnose] {label}: {cfg.data.get(key) or finder()}")
                except FileNotFoundError as e:
                    print(f"[Diagnose] {label}: ❌ {e}")

        # Whisper / GPU diagnostics
        try:
            from phonotype.paths import find_whisper_cli
            from phonotype.core.transcriber import probe_whisper_gpu_capability
            wc = find_whisper_cli()
            print(f"[Diagnose] whisper-cli: {wc}")
            gpu_cfg = bool(cfg.data.get("whisper_gpu_enabled", True))
            print(f"[Diagnose] config whisper_gpu_enabled: {gpu_cfg}")
            # Multi-GPU: show the Vulkan GPU drivers and which one gets pinned.
            try:
                from phonotype.core.transcriber import (
                    find_gpu_icd, _list_vulkan_icd_files, _icd_vendor,
                )
                gpu_icds = [(p, _icd_vendor(p)) for p in _list_vulkan_icd_files()]
                gpu_icds = [(p, v) for (p, v) in gpu_icds
                            if v in ("nvidia", "amd", "intel")]
                if len(gpu_icds) > 1:
                    pref = str(cfg.data.get("whisper_gpu_device", "auto") or "auto")
                    icd, vendor = find_gpu_icd(pref)
                    print(f"[Diagnose] config whisper_gpu_device: {pref}")
                    print(f"[Diagnose] Vulkan GPU drivers ({len(gpu_icds)}):")
                    for p, v in gpu_icds:
                        mark = "  ← pinned" if (icd is not None and p == icd) else ""
                        print(f"[Diagnose]   {v}: {p}{mark}")
                    if icd is not None:
                        print(f"[Diagnose] → restricting Vulkan to {vendor.upper()} via "
                              "VK_DRIVER_FILES so whisper.cpp avoids the iGPU")
                    else:
                        print("[Diagnose] → no preferred discrete GPU driver found; "
                              "whisper picks Vulkan device 0")
            except Exception:
                pass
            cap = probe_whisper_gpu_capability(wc)
            if cap["capable"] is True:
                print(f"[Diagnose] whisper-cli build: ✅ GPU-capable ({cap['backend']})")
                if not gpu_cfg:
                    print("[Diagnose] → GPU build present but disabled in config; "
                          "set whisper_gpu_enabled: true to use it.")
                else:
                    print("[Diagnose] → Set 'verbosity: true' to log the live backend per transcription;")
                    print("[Diagnose]   if it logs 'CPU' the GPU device/driver isn't usable at run time.")
            elif cap["capable"] is False:
                print("[Diagnose] whisper-cli build: ⚠️ CPU-only (no GPU backend compiled in)")
                if gpu_cfg:
                    print("[Diagnose] → whisper_gpu_enabled is true but this binary has no GPU "
                          "support, so transcription runs on CPU regardless.")
                    print("[Diagnose] → To enable GPU: rebuild whisper.cpp with "
                          "'./setup.sh --gpu' (CUDA/Vulkan).")
            else:
                print(f"[Diagnose] whisper-cli build: ❓ could not determine ({cap['detail']})")
        except FileNotFoundError:
            print("[Diagnose] whisper-cli: ❌ not found (run ./setup.sh)")
        except Exception as e:
            print(f"[Diagnose] whisper-cli check failed: {e}")

        # Verbose file-log location
        try:
            from phonotype.paths import LOG_DIR
            vfile = LOG_DIR / "phonotype.log"
            if bool(cfg.data.get("verbosity", False)):
                print(f"[Diagnose] log file: {vfile} (rotating; errors + verbose, verbosity on)")
            else:
                print(f"[Diagnose] log file: {vfile} (rotating; errors only — set 'verbosity: true' for full verbose)")
        except Exception:
            pass

        sys.exit(0)

    # Optionally ensure mic is on and set to desired level (best-effort)
    _mic_autoset_if_enabled(cfg)

    print()
    _print_boxed(f"Phonotype app, in '{ORANGE}{mode}{RESET}' mode.")
    # show shortcut hint
    print(f"""Note:
- create a global {ORANGE}HOTKEY{RESET} shortcut (in your system) that runs {ORANGE}`bash -c 'phonotype --trigger-record'`{RESET} (e.g. Super+Z)"
- start hotkey-triggered voice-typing by running in terminal {ORANGE}'phonotype --rh'{RESET} or {ORANGE}'phonotype --tray'{RESET}.
- advised: have Phonotype always ready in the background, by enabling autostart: {ORANGE}`phonotype --autostart true`{RESET}.
- transcripts ALWAYS picked up into clipboard.
""")

    if mode == "cli":
        # Forward unknown args to cli_main
        from phonotype.cli import cli_main as cli_main_mod
        sys.argv = [sys.argv[0]] + unknown
        cli_main_mod.main()
    elif mode == "tray":
        from phonotype.tray.tray_main import main as tray_main
        tray_main()
    else:
        print(f"[__main__] ❌ Unknown app_mode: {mode}")
        sys.exit(1)

if __name__ == "__main__":
    main()

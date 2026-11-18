# Phonotype

Voice typing for Linux: press a hotkey, speak, press again — the text is typed into
whatever window has focus. Speech is recognised on your own machine (whisper.cpp or
NVIDIA Parakeet); an optional LLM pass can turn a rough dictation into a clean request.

Phonotype is an independent continuation of [VOXD](https://github.com/jakovius/voxd)
by Jakov Ivkovic (MIT). It is not affiliated with or endorsed by the VOXD project.

## Supported platform

| | Supported and tested | Should work, not tested |
|---|---|---|
| Distribution | Gentoo | any distribution, from source |
| Init system | OpenRC (user services) | systemd user units |
| Session | KDE Plasma on Wayland (`ydotool`) | X11 (`xdotool`), other desktops |
| Compute | NVIDIA CUDA, CPU | Vulkan |
| Python | 3.12+ | — |

Everything in the right-hand column is kept in the tree but nobody checks it before a
release. Reports and patches are welcome; there is no guarantee.

What Phonotype is: a tray application with a settings window, plus a small command-line
interface for the hotkey, diagnostics and scripting.

## Installation

### Gentoo

```bash
eselect repository add badger git https://github.com/deepbadger/gentoo-overlay.git
emerge --sync badger
emerge app-accessibility/phonotype        # USE=gigachat adds the GigaChat provider
gpasswd -a "$USER" input                  # ydotoold needs /dev/uinput; log in again
```

The package does not ship the recognition binaries. Build them once from a checkout of
this repository (they are linked into `~/.local/bin`):

```bash
./setup.sh --gpu=cuda --no-venv     # or --gpu (auto-detect), or no flag for CPU
```

### From source (any distribution)

Needs `git`, `cmake`, a C++ compiler, Python 3.12+, PortAudio, `ffmpeg`, and
`ydotool` (Wayland) or `xdotool` (X11) plus a clipboard tool (`wl-clipboard`, `xclip`).

```bash
git clone https://github.com/deepbadger/phonotype.git && cd phonotype
./setup.sh                 # builds whisper.cpp and creates .venv
.venv/bin/phonotype --tray
```

### Coming from VOXD

On first start Phonotype imports `~/.config/voxd` (settings, API keys) and
`~/.local/share/voxd` (models are hard-linked, so they take no extra space). The old
directories are left untouched and can be deleted afterwards. Two things have to be
changed by hand:

- the global hotkey command: `voxd --trigger-record` → `phonotype --trigger-record`;
- autostart: remove the `voxd-tray` service and add `phonotype-tray` (below).

Flux mode, the main window (`--gui`) and the built-in llama.cpp server are gone; a
config that still selects `llamacpp_server` falls back to `ollama`.

## Getting started

1. **Bind a global hotkey** in your desktop settings to:
   ```
   bash -c 'phonotype --trigger-record'
   ```
2. **Start the tray**: `phonotype --tray`. To start it with the session:
   ```bash
   # OpenRC user services
   rc-update --user add phonotype-ydotoold default
   rc-update --user add phonotype-tray default
   # or, with systemd: phonotype --autostart true
   ```
3. **Get a speech model**: tray menu → *Model* → *Manage models…*, pick one and press
   *Download and use*.
4. Press the hotkey, speak, press it again.

## Speech models

Settings → **Models** lists what is on disk (engine, size, *Use* / *Delete*) and a
catalogue to download from. The tray's *Model* submenu switches between installed
models with one click. The same from a terminal:

```bash
phonotype-model list
phonotype-model install parakeet-tdt-0.6b-v3-q8_0
phonotype-model use parakeet-tdt-0.6b-v3-q8_0      # also selects the engine
phonotype-model remove tiny
```

Two engines, chosen by the model you activate (`asr_engine` in the config):

- **Parakeet** (`parakeet-tdt-0.6b-v3`, 25 European languages incl. Russian) — detects
  the language itself, writes punctuation, does not invent text on silence, and is
  several times faster on short phrases. Variants: f16 (1.3 GB), `-q8_0`, `-q4_k`.
- **Whisper** — any `ggml-*.bin` model, 99 languages; set `language` (or `auto`).

Any valid whisper.cpp GGML file dropped into `~/.local/share/phonotype/models/` shows
up automatically. `./add-hf-model.sh <hf-repo> <name> [--quantize q5_0]` converts a
HuggingFace Whisper checkpoint (for example a language-specific fine-tune).

To compare engines on your own recordings: `tools/bench_asr.py`.

## AI post-processing

Optional: the transcript is sent to an LLM with a prompt before it is typed. Everything
is on Settings → **AI processing**; the tray menu switches it on and off and picks the
prompt.

- **Providers**: `openrouter`, `openai`, `anthropic`, `xai`, `gigachat`,
  `openai_compatible` (your own endpoint), and `ollama` on localhost.
- **API key**: paste it in the settings (stored in `~/.config/phonotype/keys.env`,
  mode 0600) or export the provider's variable (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `XAI_API_KEY`, `GIGACHAT_CREDENTIALS`). A tray started by the
  session usually does not see variables from a shell profile. The page shows where
  the current key comes from.
- **Proxy**: `socks5://host:1080` or `http://user:password@host:3128`
  (`aipp_proxy`). With SOCKS5 host names are resolved by the proxy. Local endpoints
  and GigaChat are never proxied. *Test connection* checks the route.
- **Prompts**: four slots. The shipped ones turn a dictation into a request for
  another LLM — *clean up the request*, *task statement*, *instruction for a coding
  agent*. They tell the model to rewrite, not to answer.
- **Temperature**: `aipp_temperature`, 0.2 by default.

## Configuration

Settings are edited in the settings window and stored in
`~/.config/phonotype/config.yaml`; data (models, recordings, logs, metrics) lives in
`~/.local/share/phonotype/`. Useful keys:

| Key | Meaning |
|---|---|
| `asr_engine` | `whisper` or `parakeet` |
| `language` | Whisper language (ISO 639-1 or `auto`); ignored by Parakeet |
| `whisper_gpu_enabled`, `whisper_gpu_device`, `whisper_vram_check` | GPU use (both engines) |
| `typing_delay`, `paste_unicode`, `ctrl_v_paste` | how the text reaches the window |
| `save_recordings` | keep the audio of every dictation |
| `aipp_*` | AI post-processing |

Environment overrides for development: `PHONOTYPE_WC_BIN`, `PHONOTYPE_PARAKEET_BIN`,
`PHONOTYPE_MODEL_PATH`, `PHONOTYPE_PARAKEET_MODEL_PATH`.

## Command line

```bash
phonotype --tray                 # the application
phonotype --trigger-record       # start/stop recording in the running instance (hotkey)
phonotype --diagnose             # binaries, models, ydotool, audio devices, GPU build
phonotype --setup                # create config and launcher, report what is missing
phonotype --version
phonotype                        # interactive CLI ('h' for commands); --rh, --transcribe, --aipp …
```

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Hotkey does nothing | Phonotype is not running, or the hotkey still calls `voxd`. Run `phonotype --trigger-record` in a terminal. |
| Text is recognised but not typed | Wayland: `ydotoold` is not running or you are not in the `input` group. `phonotype --diagnose` shows the daemon state. |
| Empty or poor transcript | Microphone level too high (clipping) or the wrong input device — Settings → Audio. |
| Recognition is slow | GPU not used: `phonotype --diagnose` shows whether `whisper-cli` was built with a GPU backend; a desktop that has eaten the VRAM forces the CPU. |
| "No model" | Download one on Settings → Models. Parakeet also needs `parakeet-cli` on `PATH` (`./setup.sh`). |
| AI processing returns the raw text | Missing key or unreachable provider — see the hint under *API key* and use *Test connection*; errors go to `~/.local/share/phonotype/logs/`. |

## Development

```bash
./setup.sh                        # whisper.cpp + .venv with an editable install
.venv/bin/pip install pytest
.venv/bin/pytest                  # the suite stubs audio, clipboard and the recogniser
./release.sh 2.1.0                # bump pyproject.toml, tag, push → GitHub release
```

Layout: `src/phonotype/core` (recorder, transcriber, AI processing, config),
`tray/` and `gui/settings_window.py` (interface), `cli/`, `models.py` (catalogue and
inventory), `paths.py` (all filesystem look-ups), `migrate.py` (import from VOXD).

## License

MIT, see [LICENSE](LICENSE). Based on VOXD © 2025 Jakov Ivkovic; third-party notices
are in [THIRD_PARTY_LICENSES](THIRD_PARTY_LICENSES). The icons are original to
Phonotype (`tools/make_icons.py`).

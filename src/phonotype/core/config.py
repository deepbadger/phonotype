import yaml
import shutil
import os
from pathlib import Path
import re
from platformdirs import user_config_dir
try:
    from importlib.resources import files
except Exception:  # Python <3.9 (e.g., openSUSE Leap)
    from importlib_resources import files  # type: ignore
from phonotype.paths import resolve_whisper_binary, resolve_model_path, DATA_DIR  # <-- add this import
from phonotype.utils.languages import ISO_639_1, normalize_lang_code, is_valid_lang

# ---------------------------------------------------------------------------
#   AIPP prompts. The transcript is appended on a new line after the prompt,
#   hence the closing "---".
# ---------------------------------------------------------------------------
PROMPT_CLEAN_REQUEST = """You are a dictation post-processor. The text after the line "---" is a raw speech-to-text transcript of a user dictating a request for an AI assistant. Rewrite it as the message the user meant to type.

Rules:
- Do not answer, execute or comment on the request. Your output is the request itself, rewritten.
- Write in the same language the user spoke.
- Keep the meaning and every specific detail: names, numbers, file paths, commands, code identifiers.
- Remove filler words, false starts and repetitions. When the user corrects themselves, keep only the final version.
- Fix punctuation, capitalization and obvious recognition errors. Restore technical terms that were transcribed phonetically (e.g. "пайтон" → Python, "гит хаб" → GitHub).
- Do not add requirements, assumptions or details the user did not say.

Output only the rewritten text: no preamble, no quotes, no explanations.
---"""

PROMPT_TASK_STATEMENT = """You are a dictation post-processor. The text after the line "---" is a raw speech-to-text transcript in which a user describes a task for an AI assistant. Turn it into a clear task statement that the assistant can act on.

Rules:
- Do not perform the task and do not answer it. Output only the task statement.
- Write in the same language the user spoke.
- Start with one sentence stating the goal. Then, only if the user mentioned them, list context, constraints and the expected result as short bullet points.
- Reorder thoughts so that related points are together; drop filler, repetitions and abandoned phrasings.
- Keep every specific detail exactly: names, numbers, paths, commands, identifiers. Fix terms that were transcribed phonetically.
- Do not invent requirements. If something the user said is ambiguous, keep it as said rather than guessing.

Output only the task statement: no preamble, no quotes, no commentary.
---"""

PROMPT_CODING_INSTRUCTION = """You are a dictation post-processor. The text after the line "---" is a raw speech-to-text transcript of a developer dictating an instruction for a coding agent. Rewrite it as a precise instruction.

Rules:
- Do not write code and do not carry out the instruction. Output only the rewritten instruction.
- Write in the same language the developer spoke; keep code, commands and identifiers in their original form.
- Put file names, paths, commands, function and variable names in backticks. Restore identifiers and tool names that were transcribed phonetically or split into words.
- If several actions are requested, give them as a numbered list in the order they should be done.
- State explicitly what must not be changed or done, if the developer said so.
- Remove filler, repetitions and self-corrections; keep only the final intent. Do not add steps or requirements that were not dictated.

Output only the instruction: no preamble, no quotes, no commentary.
---"""

# Prompts shipped before 1.7.0+mir.6. A config still holding one of them
# unchanged is moved to the current text; an edited prompt is left alone.
LEGACY_PROMPTS = {
    "default": 'Rewrite the following input so that it is clean and concise. Do not add any additional text or commentary. Just the rewritten text.',
    "prompt1": 'Interpret the following text to the best of your ability as a C programming language code and output it as such. Do not add any additional text or commentary. Just the corresponding C code.',
    "prompt2": 'Interpret the following text to the best of your ability as a Python programming language code and output it as such. Do not add any additional text or commentary. Just the corresponding Python code.',
}

AIPP_PROVIDERS = ("ollama", "openai", "openrouter", "anthropic", "xai", "gigachat", "openai_compatible")
OBSOLETE_PREFIXES = ("flux_", "llamacpp_")

DEFAULT_CONFIG = {
    "perf_collect": False,
    "perf_accuracy_rating_collect": True,
    "log_enabled": True,
    # Dictation history on disk (core/history.py); 0 days keeps everything.
    "history_enabled": True,
    "history_days": 30,
    "log_location": "",
    "typing": True,
    "typing_delay": 1,
    "typing_start_delay": 0.15,
    "ctrl_v_paste": False,  # Use Ctrl+V instead of default Ctrl+Shift+V
    # When True, non-ASCII text (e.g. Cyrillic) is delivered via clipboard paste
    # instead of ydotool/xdotool 'type'. Keycode-based typing is layout-dependent
    # and silently drops keys that don't map under the active keyboard layout.
    "paste_unicode": True,
    # When the typer routes text through clipboard paste, snapshot the user's
    # current clipboard before overwriting and restore it afterwards so the
    # paste doesn't clobber whatever they had copied.
    "paste_preserve_clipboard": True,
    "paste_restore_delay_ms": 200,
    "append_trailing_space": True,
    "verbosity": False,
    "autostart": False,
    "save_recordings": False,
    # Recording behavior
    "record_chunked": True,
    "record_chunk_seconds": 300,
    # Audio preprocessing
    "audio_preproc_enabled": True,
    "audio_peak_dbfs": -3.0,
    "audio_clip_warn_threshold": 0.01,
    # Audio device preferences
    "audio_prefer_pulse": True,
    "audio_input_device": "",
    # Mic autoset (best-effort; uses wpctl/pactl/amixer if present)
    "mic_autoset_enabled": True,
    "mic_autoset_level": 0.45,
    # Speech-recognition engine:
    #   "whisper"  – whisper-cli + whisper_model_path (multilingual, slowest);
    #   "parakeet" – parakeet-cli from the same whisper.cpp build + NVIDIA
    #                parakeet-tdt-0.6b-v3 (25 European languages incl. Russian,
    #                language auto-detected; several times faster, less VRAM,
    #                fast enough on CPU). The whisper_gpu_* / vram_check keys
    #                apply to both engines.
    "asr_engine": "whisper",
    # Empty → auto-detect (see phonotype.paths.find_parakeet_cli / find_parakeet_model).
    "parakeet_binary": "",
    "parakeet_model_path": "",
    "whisper_binary": "whisper.cpp/build/bin/whisper-cli",
    "whisper_model_path": "whisper.cpp/models/ggml-base.en.bin",
    "language": "en",
    # Use the GPU when the whisper-cli binary was built with a GPU backend
    # (CUDA/Vulkan). A CPU-only binary ignores this. When False, phonotype passes
    # -ng/--no-gpu to force CPU even on a GPU build.
    "whisper_gpu_enabled": True,
    # Which GPU to use when several drivers are present (e.g. an integrated iGPU
    # + a discrete NVIDIA card on a Vulkan build). phonotype restricts the Vulkan
    # loader to the chosen driver via VK_DRIVER_FILES. "auto" picks the discrete
    # NVIDIA driver; "nvidia"/"amd"/"intel" force a specific vendor. Only affects
    # Vulkan builds.
    "whisper_gpu_device": "auto",
    # Just before each transcription, check free VRAM via nvidia-smi and go
    # straight to CPU (-ng) when the model clearly cannot fit — a long desktop
    # session (browser, compositor) can exhaust the card, and the doomed GPU
    # attempt costs extra seconds. No effect when nvidia-smi is unavailable.
    "whisper_vram_check": True,
    # Pass -fa (flash attention) to whisper-cli: faster and smaller compute
    # buffers, which helps on VRAM-tight cards. Auto-disabled for the session
    # when the installed whisper-cli rejects the flag. Off by default because
    # some Vulkan driver/device combos handle flash attention poorly.
    "whisper_flash_attn": False,
    # Start the recogniser when recording starts, so the model loads while
    # the user speaks (the audio is piped to it when recording stops).
    "asr_prewarm": True,

    # Drop transcripts that consist solely of a known Whisper hallucination
    # (the "subscribe to my channel" boilerplate it emits on silence/noise).
    # Names and terms to spell a fixed way: [{"term": ..., "sounds_like": [...]}].
    # See core/vocabulary.py; edited on Settings → Vocabulary.
    "vocabulary": [],
    "hallucination_filter_enabled": True,
    "hallucination_blocklist": [
        "Подписывайтесь на мой канал, ставьте лайки и пишите комментарии.",
        "Подписывайтесь на канал.",
        "Спасибо за просмотр!",
        "Продолжение следует...",
        "Субтитры сделал DimaTorzok",
        "Субтитры создавал DimaTorzok",
        "Редактор субтитров А.Семкин Корректор А.Егорова",
        "Thanks for watching!",
        "Please subscribe to my channel.",
        "Like and subscribe.",
    ],

    # --- AIPP (AI post-processing) ---------------------------------------------
    "aipp_enabled": False,
    "aipp_provider": "ollama",                    # ollama / openai / openrouter / anthropic / xai / gigachat / openai_compatible
    "aipp_active_prompt": "default",

    # New: List of models per provider
    "aipp_models": {
        "ollama": ["llama3.2:latest", "mistral:latest", "gemma3:latest", "qwen2.5-coder:1.5b"],
        "openai": ["gpt-4o-mini-2024-07-18"],
        "openrouter": ["openai/gpt-4o-mini", "anthropic/claude-3.5-sonnet", "meta-llama/llama-3.1-8b-instruct"],
        "anthropic": ["claude-3-opus-20240229", "claude-3-haiku"],
        "xai": ["grok-3-latest"],
        "gigachat": ["GigaChat-2-Max", "GigaChat-2-Pro", "GigaChat-2", "GigaChat"],
        "openai_compatible": ["custom-model"]
    },

    # New: Selected model per provider
    "aipp_selected_models": {
        "ollama": "gemma3:latest",
        "openai": "gpt-4o-mini-2024-07-18",
        "openrouter": "openai/gpt-4o-mini",
        "anthropic": "claude-3-opus-20240229",
        "xai": "grok-3-latest",
        "gigachat": "GigaChat-2-Max",
        "openai_compatible": "custom-model"
    },

    "aipp_openai_compatible_base_url": "",
    "aipp_openai_compatible_api_key": "",
    "aipp_temperature": 0.2,                       # low: rewrite faithfully, don't improvise
    "aipp_proxy": "",                              # proxy for cloud providers: http://host:port, socks5://host:port

    # GigaChat (Sber) settings
    "gigachat_scope": "GIGACHAT_API_PERS",         # GIGACHAT_API_PERS | GIGACHAT_API_CORP
    "gigachat_verify_ssl": True,                   # set False if Russian Trusted Root CA is missing

    


    "aipp_prompts": {
        "default": PROMPT_CLEAN_REQUEST,
        "prompt1": PROMPT_TASK_STATEMENT,
        "prompt2": PROMPT_CODING_INSTRUCTION,
        "prompt3": "Rewrite the following text as a three-verse poem.",
    }
}

CONFIG_DIR = Path(user_config_dir("phonotype"))
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "config.yaml"
_TPL = files("phonotype.defaults").joinpath("default_config.yaml")
# first run?  copy pristine template
if not CONFIG_PATH.exists():
    shutil.copy(_TPL, CONFIG_PATH)


class AppConfig:
    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()
        self._validate_aipp_config()

    def load(self):
        if CONFIG_PATH.exists():
            with open(CONFIG_PATH, "r") as f:
                user_config = yaml.safe_load(f) or {}
                self.data.update(user_config)

        # Backward-compat: migrate legacy 'model_path' → 'whisper_model_path'
        updated = False
        if "whisper_model_path" not in self.data and "model_path" in self.data:
            self.data["whisper_model_path"] = self.data.get("model_path", "")
            updated = True

        # Always resolve absolute paths for whisper_binary and whisper_model_path
        abs_whisper = str(resolve_whisper_binary(self.data.get("whisper_binary", "")))
        abs_model = str(resolve_model_path(self.data.get("whisper_model_path", self.data.get("model_path", ""))))
        updated = False
        if self.data.get("whisper_binary") != abs_whisper:
            self.data["whisper_binary"] = abs_whisper
            updated = True
        if self.data.get("whisper_model_path") != abs_model:
            self.data["whisper_model_path"] = abs_model
            updated = True

        # Drop settings of features that no longer exist (Flux, llama.cpp server)
        for key in [k for k in self.data if k.startswith(OBSOLETE_PREFIXES)]:
            del self.data[key]
            updated = True

        # Normalize and validate language
        try:
            lang = normalize_lang_code(self.data.get("language", "en"))
            if not is_valid_lang(lang):
                print(f"[config] Invalid language '{self.data.get('language')}', falling back to 'en'")
                lang = "en"
            if self.data.get("language") != lang:
                self.data["language"] = lang
                updated = True
        except Exception:
            self.data["language"] = "en"
            updated = True

        # Assign config values to attributes
        for k, v in self.data.items():
            setattr(self, k, v)

        self.log_location = self.data.get("log_location", "")

        # Save config if any path was updated
        if updated:
            self.save()

    def save(self):
        with open(CONFIG_PATH, "w") as f:
            yaml.dump(self.data, f, default_flow_style=False)
        # print("\n[config] Configuration saved.")

    def set(self, key, value):
        if key not in DEFAULT_CONFIG:
            print(f"\n[config] Unknown key: {key}")
            return
        self.data[key] = value
        setattr(self, key, value)
        print(f"\n[config] Updated: {key} = {value}")

    def validate(self):
        print("\n[config] Validating config...")

        def check_file(path, label):
            if not os.path.exists(path):
                print(f"  ❌ {label} not found: {path}")
            else:
                print(f"  ✅ {label} found: {path}")

        engine = str(self.data.get("asr_engine", "whisper")).strip().lower()
        if engine not in ("whisper", "parakeet"):
            print(f"  ⚠️ Invalid asr_engine: {engine} (allowed: whisper, parakeet)")
        if engine == "parakeet":
            from phonotype.paths import find_parakeet_cli, find_parakeet_model
            for key, finder, label in (("parakeet_model_path", find_parakeet_model, "Parakeet model"),
                                       ("parakeet_binary", find_parakeet_cli, "parakeet-cli")):
                path = self.data.get(key) or ""
                if not path:
                    try:
                        path = finder()
                    except FileNotFoundError:
                        path = "(not found)"
                check_file(path, label)
        else:
            check_file(self.whisper_model_path, "Model file")
            check_file(self.whisper_binary, "Whisper binary")

        if self.aipp_provider not in AIPP_PROVIDERS:
            print(f"  ⚠️ Invalid AIPP provider: {self.aipp_provider}")

        # typing_delay: allow 0 (→ instant paste) up to 1 s per char
        if not isinstance(self.typing_delay, (int, float)) or not (0 <= self.typing_delay <= 1):
            print(f"  ⚠️ Typing delay out of range: {self.typing_delay} (allowed 0–1)")

        if not isinstance(self.typing_start_delay, (int, float)) or not (0.0 <= self.typing_start_delay <= 5):
            # Using .data avoids mypy complaints about dynamic attrs
            val = self.data.get("typing_start_delay", 0.15)
            if not isinstance(val, (int, float)) or not (0.0 <= val <= 5):
                print(f"  ⚠️ typing_start_delay out of range: {val}")

        if self.aipp_provider == "openai" and not os.getenv("OPENAI_API_KEY"):
            print("  ⚠️ OPENAI_API_KEY not set in environment.")
        if self.aipp_provider == "openrouter" and not os.getenv("OPENROUTER_API_KEY"):
            print("  ⚠️ OPENROUTER_API_KEY not set in environment.")
        if self.aipp_provider == "anthropic" and not os.getenv("ANTHROPIC_API_KEY"):
            print("  ⚠️ ANTHROPIC_API_KEY not set in environment.")
        if self.aipp_provider == "xai" and not os.getenv("XAI_API_KEY"):
            print("  ⚠️ XAI_API_KEY not set in environment.")
        if self.aipp_provider == "gigachat" and not os.getenv("GIGACHAT_CREDENTIALS"):
            print("  ⚠️ GIGACHAT_CREDENTIALS not set in environment.")
        if self.aipp_provider == "openai_compatible":
            if not self.data.get("aipp_openai_compatible_base_url"):
                print("  ⚠️ aipp_openai_compatible_base_url not set in config.")
            if not self.data.get("aipp_openai_compatible_api_key"):
                print("  ⚠️ aipp_openai_compatible_api_key not set in config.")

        # Warn if non-English language is set but an English-only (*.en) model is configured
        try:
            if self.data.get("language") != "en":
                mp = str(self.data.get("whisper_model_path", "")).lower()
                if mp.endswith(".en.bin"):
                    print("  ⚠️ Non-English language selected but an English-only (*.en) model is configured. Use a multilingual model (e.g., base/small/medium/large-v3).")
        except Exception:
            pass

        print("\n[config] Validation complete.")

    def print_summary(self):
        print("\n[config] Current Settings:")
        for k, v in self.data.items():
            print(f"  {k}: {v}")

    def list_models(self):
        """Return all model files in the canonical data dir."""
        model_dir = DATA_DIR / "models"
        print("\nAvailable models:")
        if not model_dir.exists():
            print("  No model directory found.")
            return []

        models = sorted(model_dir.glob("*.bin"))
        for m in models:
            print(f"  {m.name}")
        return models

    def select_model(self, model_name):
        """Set the active model to *model_name* found in DATA_DIR/models."""
        model_path = DATA_DIR / "models" / model_name
        if not model_path.exists():
            print(f"\n[config] Model not found: {model_path}")
            return
        abs_model_path = str(model_path.resolve())
        self.set("whisper_model_path", abs_model_path)
        self.save()
        print(f"\n[config] Model switched to {model_name}")
    
    # ---- AIPP helpers --------------------------------------------------
    def current_prompt(self) -> str:
        return self.data["aipp_prompts"].get(self.data["aipp_active_prompt"], "")

    def set_prompt(self, key: str, value: str):
        if key not in self.data["aipp_prompts"]:
            print(f"\n[config] Unknown prompt slot: {key}")
            return
        self.data["aipp_prompts"][key] = value
        self.save()

    def get_aipp_models(self, provider=None):
        """Return list of models for the given provider (or current provider)."""
        if provider is None:
            provider = self.data.get("aipp_provider", "ollama")
        return self.data.get("aipp_models", {}).get(provider, [])

    def get_aipp_selected_model(self, provider=None):
        """Return the selected model for the given provider (or current provider)."""
        if provider is None:
            provider = self.data.get("aipp_provider", "ollama")
        return self.data.get("aipp_selected_models", {}).get(provider, "")

    def set_aipp_selected_model(self, model_name, provider=None):
        """Set the selected model for the given provider (or current provider)."""
        if provider is None:
            provider = self.data.get("aipp_provider", "ollama")
        if model_name not in self.get_aipp_models(provider):
            print(f"\n[config] Model '{model_name}' not in aipp_models for provider '{provider}'")
            return
        self.data["aipp_selected_models"][provider] = model_name
        self.save()
        print(f"\n[config] AIPP model for {provider} set to {model_name}")

    def _validate_aipp_config(self):
        """Ensure aipp_prompts and aipp_models/selected_models are valid."""
        prompts = self.data.get("aipp_prompts", {})
        for slot in ["default", "prompt1", "prompt2", "prompt3"]:
            if slot not in prompts:
                prompts[slot] = ""
        for k in list(prompts.keys()):
            if k not in ["default", "prompt1", "prompt2", "prompt3"]:
                del prompts[k]
        for slot, legacy in LEGACY_PROMPTS.items():
            if prompts.get(slot) == legacy:
                prompts[slot] = DEFAULT_CONFIG["aipp_prompts"][slot]
        self.data["aipp_prompts"] = prompts

        active = self.data.get("aipp_active_prompt", "default")
        if active not in prompts:
            print(f"\n[config] Invalid aipp_active_prompt '{active}', resetting to 'default'")
            self.data["aipp_active_prompt"] = "default"

        valid_providers = list(AIPP_PROVIDERS)
        for table in ("aipp_models", "aipp_selected_models"):
            if isinstance(self.data.get(table), dict):
                self.data[table].pop("llamacpp_server", None)      # provider removed in 2.0
        provider = self.data.get("aipp_provider", "ollama")
        if provider not in valid_providers:
            print(f"\n[config] Invalid aipp_provider '{provider}', resetting to 'ollama'")
            self.data["aipp_provider"] = "ollama"

        # Ensure aipp_models and aipp_selected_models have all providers.
        # A user's config.yaml replaces the whole aipp_models/aipp_selected_models
        # dicts on load, so providers added in newer versions are missing for
        # existing installs. Backfill from DEFAULT_CONFIG (not an empty list) so
        # their model dropdowns aren't blank.
        default_models = DEFAULT_CONFIG.get("aipp_models", {})
        default_selected = DEFAULT_CONFIG.get("aipp_selected_models", {})
        for prov in valid_providers:
            cur = self.data.get("aipp_models", {}).get(prov)
            if not cur and default_models.get(prov):
                self.data["aipp_models"][prov] = list(default_models[prov])
            elif prov not in self.data.get("aipp_models", {}):
                self.data["aipp_models"][prov] = list(default_models.get(prov, []))
            if not self.data.get("aipp_selected_models", {}).get(prov):
                models = self.data["aipp_models"][prov]
                self.data["aipp_selected_models"][prov] = (
                    default_selected.get(prov)
                    or (models[0] if models else "")
                )

    @property
    def aipp_model(self):
        """Shortcut for current provider's selected model."""
        prov = self.data.get("aipp_provider", "ollama")
        return self.data.get("aipp_selected_models", {}).get(prov, "")

    @aipp_model.setter
    def aipp_model(self, value):
        prov = self.data.get("aipp_provider", "ollama")
        self.set_aipp_selected_model(value, prov)

# Global singleton holder (defined after AppConfig)
_APP_CONFIG = None

def get_config():
    """Return the shared AppConfig instance (create on first call)."""
    global _APP_CONFIG
    if _APP_CONFIG is None:
        _APP_CONFIG = AppConfig()
    return _APP_CONFIG
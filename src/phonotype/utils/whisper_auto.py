"""Check that the recognition binary is available.

Phonotype does not download or build binaries by itself: `whisper-cli` and
`parakeet-cli` come from a whisper.cpp build (`./setup.sh` in the repository).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

HOW_TO = ("whisper-cli was not found. Build it with './setup.sh' from the Phonotype "
          "repository (it links the binaries into ~/.local/bin), or set the path in "
          "Settings → Recognition.")


def ensure_whisper_cli(ui: Literal["cli", "gui"] = "cli") -> Path | None:
    """Return the path to whisper-cli, or None (after saying how to get it)."""
    from phonotype.paths import whisper_cli
    from phonotype.utils.libw import verr

    try:
        return whisper_cli()
    except FileNotFoundError:
        verr(f"[phonotype] {HOW_TO}")
        return None

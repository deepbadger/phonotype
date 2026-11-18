"""One-time import of settings and data from VOXD, the project Phonotype grew out of.

Runs when Phonotype starts with no config of its own and ``~/.config/voxd``
exists. Nothing is removed from the old directories.

  config   config.yaml and keys.env are copied; paths that pointed into the
           old data directory are rewritten to the new one.
  data     small files are copied; large ones (speech models) are hard-linked,
           so they take no extra disk space. If linking is impossible (another
           filesystem) a symlink to the old file is made instead.

Standard library only: this is imported by ``phonotype.paths`` before anything else.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

OLD_NAME = "voxd"
NEW_NAME = "phonotype"
MARKER = ".imported-from-voxd"
LINK_ABOVE = 64 * 1024 * 1024      # files larger than this are linked, not copied
CONFIG_FILES = ("config.yaml", "keys.env")


def _import_file(src: Path, dst: Path) -> None:
    if dst.exists() or dst.is_symlink():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.stat().st_size > LINK_ABOVE:
        try:
            os.link(src, dst)
        except OSError:
            dst.symlink_to(src)
    else:
        shutil.copy2(src, dst)


def _import_data(old: Path, new: Path) -> int:
    count = 0
    for root, _dirs, files in os.walk(old):
        rel = Path(root).relative_to(old)
        for name in files:
            src = Path(root) / name
            if not src.is_file():           # sockets, dangling links
                continue
            try:
                _import_file(src, new / rel / name.replace(OLD_NAME, NEW_NAME))
                count += 1
            except OSError:
                continue
    return count


def _import_config(old: Path, new: Path, old_data: Path, new_data: Path) -> None:
    new.mkdir(parents=True, exist_ok=True)
    for name in CONFIG_FILES:
        src = old / name
        if not src.is_file():
            continue
        dst = new / name
        if name == "config.yaml":
            text = src.read_text(encoding="utf-8")
            dst.write_text(text.replace(f"{old_data}/", f"{new_data}/"), encoding="utf-8")
        else:
            shutil.copy2(src, dst)
            os.chmod(dst, 0o600)


def import_from_voxd(config_dir: Path, data_dir: Path) -> bool:
    """Import VOXD's settings and data if Phonotype has none yet. Never raises."""
    try:
        old_config = config_dir.parent / OLD_NAME
        old_data = data_dir.parent / OLD_NAME
        if (config_dir / "config.yaml").exists() or (config_dir / MARKER).exists():
            return False
        if not (old_config / "config.yaml").is_file():
            return False
        _import_config(old_config, config_dir, old_data, data_dir)
        files = _import_data(old_data, data_dir) if old_data.is_dir() else 0
        (config_dir / MARKER).write_text(
            f"Settings and {files} data files were imported from {old_config} and {old_data}.\n"
            "The old directories are no longer used and can be deleted.\n", encoding="utf-8")
        print(f"[phonotype] Imported settings and data from VOXD ({old_config}). "
              "The old directories were left in place.", file=sys.stderr)
        return True
    except Exception as e:  # a failed import must not stop the app from starting
        print(f"[phonotype] Could not import VOXD settings: {e}", file=sys.stderr)
        return False

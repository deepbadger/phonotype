#!/usr/bin/env bash
# =============================================================================
#  Phonotype – build helper for a source checkout
#
#  Builds what the distro package does not ship:
#    • whisper.cpp → whisper-cli and parakeet-cli (optionally with a GPU backend)
#    • a Python venv with Phonotype installed in editable mode (skip with --no-venv)
#  and links the two binaries into ~/.local/bin so an installed Phonotype finds them.
#
#  It installs no system packages. Supported platform: Gentoo (see README);
#  elsewhere it should work as long as the tools below are present.
#
#  Usage:
#    ./setup.sh                 CPU build
#    ./setup.sh --gpu           auto-detect CUDA, else Vulkan, else CPU
#    ./setup.sh --gpu=cuda      NVIDIA CUDA (needs nvcc)
#    ./setup.sh --gpu=vulkan    Vulkan
#    ./setup.sh --no-venv       only build whisper.cpp
#    ./setup.sh --rebuild       wipe whisper.cpp/build first
#  The backend can also be given as PHONOTYPE_GPU=auto|cuda|vulkan|cpu.
# =============================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

msg()  { printf '==> %s\n' "$*"; }
note() { printf '\033[1;33m==>\033[0m %s\n' "$*"; }
die()  { printf '\033[0;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

PHONOTYPE_GPU="${PHONOTYPE_GPU:-cpu}"
WITH_VENV=1
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --gpu)          PHONOTYPE_GPU="auto" ;;
    --gpu=*)        PHONOTYPE_GPU="${arg#--gpu=}" ;;
    --cpu|--no-gpu) PHONOTYPE_GPU="cpu" ;;
    --no-venv)      WITH_VENV=0 ;;
    --rebuild)      REBUILD=1 ;;
    -h|--help)      sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)              die "unknown option: $arg (see --help)" ;;
  esac
done
PHONOTYPE_GPU="$(printf '%s' "$PHONOTYPE_GPU" | tr '[:upper:]' '[:lower:]')"

# ── tools ────────────────────────────────────────────────────────────────────
missing=()
for tool in git cmake python3; do
  command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
command -v c++ >/dev/null 2>&1 || command -v g++ >/dev/null 2>&1 || missing+=("c++ compiler")
if (( ${#missing[@]} )); then
  die "missing tools: ${missing[*]}  (Gentoo: emerge dev-vcs/git dev-build/cmake sys-devel/gcc)"
fi

# ── GPU backend ──────────────────────────────────────────────────────────────
detect_gpu_backend() {
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1 \
     && command -v nvcc >/dev/null 2>&1; then
    echo cuda; return
  fi
  if command -v vulkaninfo >/dev/null 2>&1 && vulkaninfo >/dev/null 2>&1; then
    echo vulkan; return
  fi
  echo cpu
}

case "$PHONOTYPE_GPU" in
  cpu|"") GPU_BACKEND=cpu ;;
  auto)   GPU_BACKEND="$(detect_gpu_backend)"
          msg "GPU auto-detect: $GPU_BACKEND" ;;
  cuda)   command -v nvcc >/dev/null 2>&1 || die "--gpu=cuda needs the CUDA toolkit (nvcc) on PATH"
          GPU_BACKEND=cuda ;;
  vulkan) GPU_BACKEND=vulkan ;;
  *)      die "unknown GPU backend '$PHONOTYPE_GPU' (auto, cuda, vulkan, cpu)" ;;
esac

# ── whisper.cpp ──────────────────────────────────────────────────────────────
if [[ ! -f whisper.cpp/CMakeLists.txt ]]; then
  if [[ -d whisper.cpp ]]; then
    # a directory without sources (e.g. only downloaded models): keep its contents
    msg "whisper.cpp/ has no sources – re-cloning (keeping its contents)."
    rm -rf whisper.cpp.stale
    mv whisper.cpp whisper.cpp.stale
  fi
  msg "Cloning whisper.cpp…"
  git clone --depth 1 https://github.com/ggml-org/whisper.cpp.git
  if [[ -d whisper.cpp.stale ]]; then
    rm -rf whisper.cpp.stale/.git
    cp -an whisper.cpp.stale/. whisper.cpp/ 2>/dev/null || true
    rm -rf whisper.cpp.stale
  fi
fi

# A build dir made for another backend must be reconfigured from scratch.
STAMP=whisper.cpp/build/.phonotype-backend
if [[ -d whisper.cpp/build ]]; then
  if (( REBUILD )) || [[ "$(cat "$STAMP" 2>/dev/null || echo unknown)" != "$GPU_BACKEND" ]]; then
    msg "Removing whisper.cpp/build to configure for $GPU_BACKEND."
    rm -rf whisper.cpp/build
  fi
fi

if [[ ! -x whisper.cpp/build/bin/whisper-cli ]]; then
  msg "Building whisper.cpp ($GPU_BACKEND) – this takes a while…"
  CMAKE_FLAGS=( -DBUILD_SHARED_LIBS=OFF )
  case "$GPU_BACKEND" in
    cuda)   CMAKE_FLAGS+=( -DGGML_CUDA=1 ) ;;
    vulkan) CMAKE_FLAGS+=( -DGGML_VULKAN=1 ) ;;
  esac
  configure() { cmake -S whisper.cpp -B whisper.cpp/build "${CMAKE_FLAGS[@]}" "$@"; }

  if [[ "$GPU_BACKEND" == cuda ]] && ! configure; then
    # nvcc caps the host compiler version (CUDA 12.9 rejects gcc 15): retry with
    # an older g++ if one is installed, else with nvcc's version-check override.
    msg "CUDA configure failed – trying an older host compiler for nvcc…"
    ok=""
    for v in 14 13 12; do
      for cand in "g++-$v" "x86_64-pc-linux-gnu-g++-$v"; do
        command -v "$cand" >/dev/null 2>&1 || continue
        rm -rf whisper.cpp/build
        if configure -DCMAKE_CUDA_HOST_COMPILER="$(command -v "$cand")"; then ok="$cand"; break 2; fi
      done
    done
    if [[ -z "$ok" ]]; then
      note "No CUDA-compatible g++ found – forcing -allow-unsupported-compiler."
      rm -rf whisper.cpp/build
      configure -DCMAKE_CUDA_FLAGS=-allow-unsupported-compiler
    fi
  elif [[ "$GPU_BACKEND" != cuda ]]; then
    configure
  fi
  cmake --build whisper.cpp/build -j"$(nproc)"
  echo "$GPU_BACKEND" > "$STAMP"
else
  msg "whisper.cpp already built ($GPU_BACKEND)."
fi

# parakeet-cli comes from the same tree; an older build dir may predate it.
if [[ ! -x whisper.cpp/build/bin/parakeet-cli && -d whisper.cpp/examples/parakeet-cli ]]; then
  msg "Building parakeet-cli…"
  cmake --build whisper.cpp/build --target parakeet-cli -j"$(nproc)" \
    || note "parakeet-cli build failed – the Parakeet engine won't be available."
fi

# ── link the binaries where an installed Phonotype looks for them ────────────────
mkdir -p "$HOME/.local/bin"
for bin in whisper-cli parakeet-cli; do
  src="$PWD/whisper.cpp/build/bin/$bin"
  dst="$HOME/.local/bin/$bin"
  [[ -x "$src" ]] || continue
  if [[ -e "$dst" && ! -L "$dst" ]]; then
    note "$dst exists and is not a symlink – left untouched."
  else
    ln -sfn "$src" "$dst"
    msg "Linked $dst"
  fi
done
case ":$PATH:" in
  *":$HOME/.local/bin:"*) ;;
  *) note "$HOME/.local/bin is not on PATH – add it, or set the binary paths in Settings → Recognition." ;;
esac

# ── Python environment ──────────────────────────────────────────────────────
if (( WITH_VENV )); then
  if [[ ! -x .venv/bin/python ]]; then
    msg "Creating .venv…"
    rm -rf .venv
    python3 -m venv .venv
  fi
  msg "Installing Phonotype into .venv (editable)…"
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e .
  msg "Run it with:  .venv/bin/phonotype --tray"
fi

msg "Done. Speech models are downloaded from Settings → Models (or: phonotype-model install <key>)."

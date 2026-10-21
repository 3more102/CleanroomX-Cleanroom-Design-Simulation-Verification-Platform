#!/usr/bin/env bash
set -eu
runtime_root=/workspace/scratch/d2477ad7a66e/runtime-packages/root
cleanroomx_display_number=$((1000 + RANDOM % 12000))
LD_LIBRARY_PATH="$runtime_root/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
  "$runtime_root/usr/bin/Xvfb" ":$cleanroomx_display_number" -screen 0 1600x1000x24 -nolisten local -nolisten unix -listen tcp -ac \
  >/workspace/scratch/d2477ad7a66e/validation/xvfb.log 2>&1 &
cleanroomx_display_pid=$!
trap 'kill "$cleanroomx_display_pid" 2>/dev/null || true' EXIT
export DISPLAY="127.0.0.1:$cleanroomx_display_number"
export LIBGL_ALWAYS_SOFTWARE=1
python - <<'PY'
import tkinter as tk,time
for _ in range(50):
    try:
        root=tk.Tk()
        root.destroy()
        break
    except tk.TclError:
        time.sleep(.1)
else:
    raise RuntimeError('X display not available')
PY
"$@"

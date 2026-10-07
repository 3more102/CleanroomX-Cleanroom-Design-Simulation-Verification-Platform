from __future__ import annotations

import os
from pathlib import Path
import sys
import traceback

from cleanroomx.gui import main


def _run() -> int:
    try:
        return main()
    except BaseException:
        # A windowed PyInstaller process has no console and may otherwise surface
        # an exception dialog that blocks non-interactive packaging health checks.
        if "--check" in sys.argv[1:]:
            diagnostic_path = os.environ.get("CLEANROOMX_CHECK_ERROR_FILE", "").strip()
            if diagnostic_path:
                try:
                    Path(diagnostic_path).write_text(
                        traceback.format_exc(),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(_run())

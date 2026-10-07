from __future__ import annotations

import sys

from cleanroomx.gui import main


def _run() -> int:
    try:
        return main()
    except BaseException:
        # A windowed PyInstaller process has no console and may otherwise surface
        # an exception dialog that blocks non-interactive packaging health checks.
        if "--check" in sys.argv[1:]:
            return 1
        raise


if __name__ == "__main__":
    raise SystemExit(_run())

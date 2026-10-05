"""PyInstaller entry point for the standalone Windows desktop build."""

from cleanroomx.gui import main


if __name__ == "__main__":
    raise SystemExit(main())

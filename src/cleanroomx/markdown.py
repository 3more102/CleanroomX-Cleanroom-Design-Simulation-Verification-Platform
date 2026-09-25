from __future__ import annotations

import html


def markdown_text(value: object) -> str:
    """Render untrusted text without allowing it to alter Markdown structure."""
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    text = html.escape(text, quote=False)
    text = text.replace("\\", "\\\\")
    for marker in ("`", "*", "_", "[", "]", "|"):
        text = text.replace(marker, "\\" + marker)
    return text.replace("\n", "<br>")

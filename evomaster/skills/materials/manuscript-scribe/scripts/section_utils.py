"""Shared helpers for section parsing in manuscript-scribe scripts."""

import re


def find_section(content: str, section: str, include_text: bool = True):
    """Return (start, end, section_text) or (start, end) for ## Section in content, or None."""
    pattern = rf"^##\s+{re.escape(section)}\s*$"
    for i, line in enumerate(content.splitlines()):
        if re.match(pattern, line.strip(), re.IGNORECASE):
            start = sum(len(line) + 1 for line in content.splitlines()[:i])
            rest = content[start:]
            match = re.search(r"\n##\s+", rest)
            end = start + (match.start() if match else len(rest))
            if include_text:
                return (start, end, content[start:end])
            return (start, end)
    return None

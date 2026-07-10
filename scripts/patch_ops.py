#!/usr/bin/env python3
from __future__ import annotations

import difflib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchDiagnostic:
    label: str
    message: str
    nearest_anchor: str | None = None

    def format(self) -> str:
        if self.nearest_anchor is None:
            return f"{self.label}: {self.message}"
        return f"{self.label}: {self.message}\nnearest anchor candidate:\n{self.nearest_anchor}"


def _nearest_block(text: str, anchor: str) -> str | None:
    if not text or not anchor:
        return None
    anchor_lines = [line for line in anchor.splitlines() if line.strip()]
    source_lines = text.splitlines()
    if not anchor_lines or not source_lines:
        return None
    window_size = min(len(source_lines), max(1, len(anchor_lines)))
    target = "\n".join(anchor_lines)
    best_ratio = 0.0
    best_window: list[str] | None = None
    for index in range(0, len(source_lines) - window_size + 1):
        window = source_lines[index : index + window_size]
        ratio = difflib.SequenceMatcher(None, target, "\n".join(window)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_window = window
    if best_window is None or best_ratio < 0.45:
        return None
    diff = difflib.unified_diff(
        anchor_lines,
        best_window,
        fromfile="expected-anchor",
        tofile="nearest-source",
        lineterm="",
    )
    return "\n".join(diff)


def ensure_text_after(text: str, anchor: str, addition: str, label: str) -> str:
    if addition in text:
        return text
    if anchor not in text:
        diagnostic = PatchDiagnostic(
            label=label,
            message="anchor not found",
            nearest_anchor=_nearest_block(text, anchor),
        )
        raise SystemExit(diagnostic.format())
    return text.replace(anchor, anchor + addition, 1)


def ensure_text_before(text: str, anchor: str, addition: str, label: str) -> str:
    if addition in text:
        return text
    if anchor not in text:
        diagnostic = PatchDiagnostic(
            label=label,
            message="anchor not found",
            nearest_anchor=_nearest_block(text, anchor),
        )
        raise SystemExit(diagnostic.format())
    return text.replace(anchor, addition + anchor, 1)


def replace_once(text: str, original: str, replacement: str, label: str) -> str:
    if replacement in text:
        return text
    if original not in text:
        diagnostic = PatchDiagnostic(
            label=label,
            message="replacement anchor not found",
            nearest_anchor=_nearest_block(text, original),
        )
        raise SystemExit(diagnostic.format())
    return text.replace(original, replacement, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True

"""Versioned prompt files.

Each prompt starts with a `version: <id>` header line, then `---`, then the text.
The version goes into every run result (and into spans in Phase 2), so a quality
change can always be tied to the exact prompt that caused it.
"""

from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Prompt:
    version: str
    text: str


def load_prompt(name: str = "triage_system") -> Prompt:
    raw = (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")
    header, sep, body = raw.partition("\n---\n")
    if not sep or not header.startswith("version:"):
        raise ValueError(f"prompt {name!r} must start with 'version: <id>' and a '---' line")
    return Prompt(version=header.removeprefix("version:").strip(), text=body.strip())

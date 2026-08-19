import json
from pathlib import Path

_MANIFEST_PATH = Path(__file__).parent.parent / "assets" / "level" / "manifest.json"


def _load() -> dict[int, str]:
    try:
        manifest = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {int(level): f"<:{data['emoji_name']}:{data['id']}>" for level, data in manifest.items()}


LEVEL_BADGES = _load()


def level_badge(level: int) -> str:
    return LEVEL_BADGES.get(level, "")

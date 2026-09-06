"""Canonical label mapping from source-dataset labels (M5 §20-21).

Only well-defined mappings are included. Ambiguous source labels are excluded from subtype
metrics rather than guessed; a coarse ``SCREEN_MONITOR_OR_LAPTOP`` option is offered for
ambiguity between laptop and monitor.
"""

from __future__ import annotations

from app.experiments.vlm.manifest import GroundTruthLabel

#: source_label (lowercased) -> canonical label.
LABEL_MAPPING: dict[str, GroundTruthLabel] = {
    "live": "LIVE",
    "genuine": "LIVE",
    "real": "LIVE",
    "phone": "SCREEN_MOBILE",
    "mobile": "SCREEN_MOBILE",
    "mobile_replay": "SCREEN_MOBILE",
    "phone_replay": "SCREEN_MOBILE",
    "laptop": "SCREEN_LAPTOP",
    "pc": "SCREEN_LAPTOP",
    "laptop_replay": "SCREEN_LAPTOP",
    "pc_replay": "SCREEN_LAPTOP",
    "tablet": "SCREEN_TABLET",
    "pad": "SCREEN_TABLET",
    "tablet_replay": "SCREEN_TABLET",
    "monitor": "SCREEN_MONITOR",
    "monitor_replay": "SCREEN_MONITOR",
    "photo": "PRINT_PHOTO",
    "a4": "PRINT_PHOTO",
    "print": "PRINT_PHOTO",
    "print_photo": "PRINT_PHOTO",
    "newspaper": "PRINT_NEWSPAPER",
    "magazine": "PRINT_MAGAZINE",
}

#: Source labels that cannot be disambiguated to a single canonical subtype.
AMBIGUOUS_LABELS: frozenset[str] = frozenset(
    {
        "screen_monitor_or_laptop",
        "monitor_or_laptop",
        "screen_or_print",
    }
)


def map_label(source_label: str) -> tuple[GroundTruthLabel | None, bool]:
    """Return (canonical_label, ambiguous). Ambiguous labels are not guessed (M5 §20)."""
    normalized = source_label.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized in AMBIGUOUS_LABELS:
        return None, True
    canonical = LABEL_MAPPING.get(normalized)
    return canonical, canonical is None

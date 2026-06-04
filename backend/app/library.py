"""Load and validate the roast library at startup.

Reads all JSON files under roast-library/, validates against Pydantic models,
and exposes a Library object that the engine queries.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .config import LIBRARY_PATH
from .models import (
    IntentDef,
    IntentsFile,
    Personality,
    PersonalityDef,
    PersonalitiesFile,
    RoastMode,
    RoastTemplate,
    SpecialTemplate,
)

log = logging.getLogger(__name__)

PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


class Library:
    """In-memory index of the entire roast library."""

    def __init__(self) -> None:
        self.roasts_by_mode: dict[RoastMode, list[RoastTemplate]] = {}
        self.roasts_by_id: dict[str, RoastTemplate] = {}
        self.personalities: dict[Personality, PersonalityDef] = {}
        self.intents: dict[str, IntentDef] = {}
        self.intent_scoring: dict = {}
        self.fallback_intent: str = "general"

        self.openers: list[SpecialTemplate] = []
        self.comebacks: list[SpecialTemplate] = []
        self.closers: list[SpecialTemplate] = []
        self.callbacks: list[SpecialTemplate] = []

        self._loaded = False

    def is_loaded(self) -> bool:
        return self._loaded

    # ----- Loading -----

    def load(self, path: Optional[Path] = None) -> None:
        path = path or LIBRARY_PATH
        if not path.exists():
            raise FileNotFoundError(f"roast-library not found at {path}")

        self._load_personalities(path / "personalities.json")
        self._load_intents(path / "intents.json")
        self._load_special(path / "openers.json", "openers")
        self._load_special(path / "comebacks.json", "comebacks")
        self._load_special(path / "closers.json", "closers")
        self._load_special(path / "callbacks.json", "callbacks")
        self._load_roasts(path / "roasts")

        self._loaded = True
        log.info(
            "library loaded: %d roasts, %d personalities, %d intents",
            len(self.roasts_by_id),
            len(self.personalities),
            len(self.intents),
        )

    def _load_personalities(self, f: Path) -> None:
        raw = _read_json(f)
        data = PersonalitiesFile.model_validate(raw)
        for key, p in data.personalities.items():
            try:
                self.personalities[Personality(key)] = p
            except ValueError:
                log.warning("unknown personality in library: %s", key)

    def _load_intents(self, f: Path) -> None:
        raw = _read_json(f)
        data = IntentsFile.model_validate(raw)
        self.intents = data.intents
        self.intent_scoring = data.scoring.model_dump()
        self.fallback_intent = data.fallback_intent

    def _load_special(self, f: Path, key: str) -> None:
        if not f.exists():
            log.warning("special file missing: %s", f)
            return
        raw = _read_json(f)
        items = raw.get(key, [])
        models: list[SpecialTemplate] = []
        for item in items:
            try:
                models.append(SpecialTemplate.model_validate(item))
            except ValidationError as e:
                log.warning("invalid %s entry %s: %s", key, item.get("id"), e)
        setattr(self, key, models)

    def _load_roasts(self, dirpath: Path) -> None:
        for f in sorted(dirpath.glob("*.json")):
            try:
                mode = RoastMode(f.stem)
            except ValueError:
                log.warning("unknown mode file: %s", f.name)
                continue
            raw = _read_json(f)
            items = raw.get("roasts", [])
            pool: list[RoastTemplate] = []
            for item in items:
                # Mode is implicit from the file name; inject it before validation.
                item_with_mode = {**item, "mode": mode.value}
                try:
                    t = RoastTemplate.model_validate(item_with_mode)
                except ValidationError as e:
                    log.warning("invalid roast %s in %s: %s", item.get("id"), f.name, e)
                    continue
                _validate_template_references(t, mode, self.personalities, f.name)
                pool.append(t)
                self.roasts_by_id[t.id] = t
            self.roasts_by_mode[mode] = pool
            log.info("loaded %d roasts for mode %s", len(pool), mode.value)

    # ----- Lookups -----

    def get_roast(self, roast_id: str) -> Optional[RoastTemplate]:
        return self.roasts_by_id.get(roast_id)

    def roasts_for_mode(self, mode: RoastMode) -> list[RoastTemplate]:
        return self.roasts_by_mode.get(mode, [])

    def all_roasts(self) -> list[RoastTemplate]:
        return list(self.roasts_by_id.values())


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ----- Validation helpers -----

def _validate_template_references(
    template: RoastTemplate,
    mode: RoastMode,
    personalities: dict[Personality, PersonalityDef],
    source_file: str,
) -> None:
    """Cross-reference check that runs after Pydantic has accepted the shape.

    Catches three classes of author mistakes that Pydantic can't:
    - placeholder names in {template} that aren't declared in placeholders{}
    - personalities[] entries whose damage range excludes template.damage
    - personalities[] entries that have this mode in their blocked_modes
    """
    # 1. Placeholder names referenced in the template body must be declared.
    referenced = set(PLACEHOLDER_RE.findall(template.template))
    declared = set(template.placeholders.keys())
    missing = referenced - declared
    if missing:
        log.warning(
            "roast %s in %s uses undeclared placeholders: %s",
            template.id, source_file, sorted(missing),
        )

    # 2. Each listed personality must accept this roast's damage value.
    # 3. Each listed personality must not block this mode.
    for p in template.personalities:
        pdef = personalities.get(p)
        if pdef is None:
            continue
        if not (pdef.min_damage <= template.damage <= pdef.max_damage):
            log.warning(
                "roast %s in %s: personality %s damage range is [%d-%d] "
                "but roast damage is %d",
                template.id, source_file, p.value,
                pdef.min_damage, pdef.max_damage, template.damage,
            )
        if mode in pdef.blocked_modes:
            log.warning(
                "roast %s in %s: personality %s blocks mode %s",
                template.id, source_file, p.value, mode.value,
            )


# Module-level singleton (lazy-initialized by main.py)
LIB = Library()

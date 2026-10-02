"""Locate the repository's adapters/ package from inside a skill's scripts/.

Works whether the skill folder is used in place or symlinked into
~/.claude/skills (the symlink is resolved). Override with CLAVIS_ADAPTERS.
"""
import os
import sys
from pathlib import Path


def repo_root():
    override = os.environ.get("CLAVIS_ADAPTERS")
    if override:
        return Path(override).resolve().parent
    here = Path(__file__).resolve()
    for p in here.parents:
        if (p / "adapters" / "taxonomy" / "__init__.py").exists():
            return p
    raise SystemExit("adapters/ not found above %s; set CLAVIS_ADAPTERS=/path/to/adapters" % here)


def taxonomy(name=None):
    root = repo_root()
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from adapters import taxonomy as t
    return t.load(name)

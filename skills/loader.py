"""Auto-discovers and loads all skill classes from this package."""
import importlib
import inspect
import pkgutil
from pathlib import Path
from .base import BaseSkill


def load_skills() -> list[BaseSkill]:
    skills = []
    pkg_dir = Path(__file__).parent
    for info in pkgutil.iter_modules([str(pkg_dir)]):
        if info.name in ("base", "loader", "__init__"):
            continue
        try:
            mod = importlib.import_module(f"skills.{info.name}")
            for _, cls in inspect.getmembers(mod, inspect.isclass):
                if issubclass(cls, BaseSkill) and cls is not BaseSkill:
                    skills.append(cls())
        except Exception as e:
            print(f"Could not load skill {info.name}: {e}")
    return sorted(skills, key=lambda s: s.name)

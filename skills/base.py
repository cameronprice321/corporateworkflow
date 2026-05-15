"""Base class every skill must inherit from."""
from abc import ABC, abstractmethod


class BaseSkill(ABC):
    name: str = "unnamed"
    description: str = ""
    icon: str = "🔧"

    @abstractmethod
    def render(self, entities: list, relationships: list, flows: list) -> None:
        """Render the skill's Streamlit UI. Called when the user selects this skill."""
        ...

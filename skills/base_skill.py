"""Base class for Claude AI skills."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """Result returned by a skill execution."""

    success: bool
    output: Any = None
    error: str = ""
    metadata: dict = field(default_factory=dict)


class BaseSkill(ABC):
    """Abstract base class for all Claude AI skills.

    Subclass this to define a skill. Each skill has a name, description,
    and an ``execute`` method that carries out the skill's logic.
    """

    name: str = ""
    description: str = ""

    def validate(self) -> None:
        """Validate that required skill attributes are set."""
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define a 'name'")
        if not self.description:
            raise ValueError(f"{self.__class__.__name__} must define a 'description'")

    @abstractmethod
    def execute(self, **kwargs) -> SkillResult:
        """Execute the skill and return a SkillResult.

        Args:
            **kwargs: Skill-specific input parameters.

        Returns:
            A :class:`SkillResult` describing the outcome.
        """

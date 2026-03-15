"""Tests for BaseSkill."""
import pytest
from skills.base_skill import BaseSkill, SkillResult


class ConcreteSkill(BaseSkill):
    """Minimal concrete skill used only in tests."""

    name = "concrete"
    description = "A test skill."

    def execute(self, **kwargs) -> SkillResult:
        return SkillResult(success=True, output="done")


class NamelessSkill(BaseSkill):
    name = ""
    description = "Missing name."

    def execute(self, **kwargs) -> SkillResult:  # pragma: no cover
        return SkillResult(success=True)


class DescriptionlessSkill(BaseSkill):
    name = "nodesc"
    description = ""

    def execute(self, **kwargs) -> SkillResult:  # pragma: no cover
        return SkillResult(success=True)


class TestSkillResult:
    def test_defaults(self):
        result = SkillResult(success=True)
        assert result.output is None
        assert result.error == ""
        assert result.metadata == {}

    def test_with_values(self):
        result = SkillResult(success=False, output="x", error="oops", metadata={"k": "v"})
        assert not result.success
        assert result.output == "x"
        assert result.error == "oops"
        assert result.metadata == {"k": "v"}


class TestBaseSkill:
    def test_concrete_skill_executes(self):
        skill = ConcreteSkill()
        result = skill.execute()
        assert result.success
        assert result.output == "done"

    def test_validate_passes_when_attributes_set(self):
        skill = ConcreteSkill()
        skill.validate()  # should not raise

    def test_validate_raises_without_name(self):
        skill = NamelessSkill()
        with pytest.raises(ValueError, match="name"):
            skill.validate()

    def test_validate_raises_without_description(self):
        skill = DescriptionlessSkill()
        with pytest.raises(ValueError, match="description"):
            skill.validate()

    def test_abstract_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            BaseSkill()  # type: ignore[abstract]

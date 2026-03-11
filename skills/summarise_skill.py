"""Summarisation skill – builds a prompt for Claude to summarise text."""
from .base_skill import BaseSkill, SkillResult


class SummariseSkill(BaseSkill):
    """Produce a concise summary prompt for a block of text.

    This skill does not call the Claude API directly; it assembles a
    ready-to-use prompt that can be passed to any ``anthropic`` client.
    This design makes the skill straightforward to test without network
    access and easy to integrate into larger workflows.

    Example::

        skill = SummariseSkill()
        result = skill.execute(text="Long article …", max_sentences=3)
        # result.output is the assembled prompt string
    """

    name = "summarise"
    description = "Build a prompt that asks Claude to summarise the supplied text."

    DEFAULT_MAX_SENTENCES = 5

    def execute(self, text: str = "", max_sentences: int = DEFAULT_MAX_SENTENCES) -> SkillResult:
        """Assemble a summarisation prompt.

        Args:
            text: The text to summarise.
            max_sentences: Maximum number of sentences in the summary.

        Returns:
            :class:`SkillResult` whose ``output`` is the assembled prompt.
        """
        self.validate()

        if not text or not text.strip():
            return SkillResult(success=False, error="'text' must be a non-empty string.")

        if max_sentences < 1:
            return SkillResult(success=False, error="'max_sentences' must be at least 1.")

        prompt = (
            f"Please summarise the following text in no more than {max_sentences} sentence(s).\n\n"
            f"Text:\n{text.strip()}"
        )
        return SkillResult(success=True, output=prompt)

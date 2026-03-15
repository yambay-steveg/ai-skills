"""Tests for SummariseSkill."""
import pytest
from skills.summarise_skill import SummariseSkill


@pytest.fixture
def skill():
    return SummariseSkill()


class TestSummariseSkill:
    def test_name_and_description(self, skill):
        assert skill.name == "summarise"
        assert skill.description

    def test_basic_execution(self, skill):
        result = skill.execute(text="The sky is blue. Water is wet.")
        assert result.success
        assert "The sky is blue" in result.output

    def test_prompt_contains_max_sentences(self, skill):
        result = skill.execute(text="Hello world.", max_sentences=2)
        assert result.success
        assert "2 sentence" in result.output

    def test_prompt_contains_original_text(self, skill):
        text = "Once upon a time there was a robot."
        result = skill.execute(text=text)
        assert result.success
        assert text in result.output

    def test_default_max_sentences(self, skill):
        result = skill.execute(text="Test text.")
        assert result.success
        assert str(SummariseSkill.DEFAULT_MAX_SENTENCES) in result.output

    def test_empty_text_returns_failure(self, skill):
        result = skill.execute(text="")
        assert not result.success
        assert result.error

    def test_whitespace_only_text_returns_failure(self, skill):
        result = skill.execute(text="   ")
        assert not result.success

    def test_zero_max_sentences_returns_failure(self, skill):
        result = skill.execute(text="Some text.", max_sentences=0)
        assert not result.success
        assert result.error

    def test_negative_max_sentences_returns_failure(self, skill):
        result = skill.execute(text="Some text.", max_sentences=-1)
        assert not result.success

    def test_text_is_stripped_in_output(self, skill):
        result = skill.execute(text="  hello world  ")
        assert result.success
        assert "hello world" in result.output
        assert "  hello world  " not in result.output

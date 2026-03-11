# ai-skills

A place to build and test [Claude](https://www.anthropic.com/claude) skills and other AI artefacts.

## Project structure

```
ai-skills/
├── skills/                  # Skill definitions
│   ├── base_skill.py        # Abstract base class every skill extends
│   ├── summarise_skill.py   # Example skill – builds a summarisation prompt
│   └── __init__.py
├── tests/                   # Pytest test suite
│   ├── test_base_skill.py
│   └── test_summarise_skill.py
├── requirements.txt
└── README.md
```

## Getting started

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. (Optional) add your Anthropic API key to a .env file
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 4. Run the tests
pytest tests/ -v
```

## Writing a new skill

1. Create a new file in `skills/`, e.g. `skills/my_skill.py`.
2. Subclass `BaseSkill` and set `name` and `description`.
3. Implement `execute(**kwargs) -> SkillResult`.
4. Export it from `skills/__init__.py`.
5. Add tests under `tests/`.

```python
from skills.base_skill import BaseSkill, SkillResult

class MySkill(BaseSkill):
    name = "my_skill"
    description = "Does something useful."

    def execute(self, input: str = "") -> SkillResult:
        self.validate()
        # build a prompt or run logic here …
        return SkillResult(success=True, output=f"Processed: {input}")
```

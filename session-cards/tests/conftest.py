"""Load the extension-less `cardctl` script as an importable module for the tests."""
import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parent.parent / "cardctl"


@pytest.fixture(scope="session")
def cc():
    # cardctl has no .py extension → give importlib an explicit source loader.
    loader = SourceFileLoader("cardctl", str(_SRC))
    spec = importlib.util.spec_from_loader("cardctl", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["cardctl"] = mod
    loader.exec_module(mod)
    return mod


class NS:
    """Tiny argparse.Namespace stand-in for calling cmd_* directly."""
    def __init__(self, **kw):
        self.__dict__.update(kw)

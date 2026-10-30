from pathlib import Path

import pytest

from knowledge_agent import load_corpus


@pytest.fixture
def data_dir():
    return Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def corpus(data_dir):
    return load_corpus(data_dir)

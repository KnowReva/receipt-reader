"""Every test: the corrections memory lives in a temporary folder, never in your home folder."""

import pytest


@pytest.fixture(autouse=True)
def _own_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("RECEIPT_MEMORY", str(tmp_path / "receipt-memory" / "memory.json"))

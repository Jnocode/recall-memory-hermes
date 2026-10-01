"""Admission regressions for the deployed runtime's goal-resume noise."""
import pytest
from recall_memory_hermes.memory_policy import should_store_turn


@pytest.mark.parametrize('text', [
    '[Continuing toward your standing goal] Remember this: continue implementation',
    '[ASYNC DELEGATION BATCH COMPLETE] Remember this: review finished',
    '[IMPORTANT: BACKGROUND PROCESS] Remember this: build finished',
])
def test_runtime_orchestration_wrappers_cannot_admit_durable_cards(text):
    assert not should_store_turn(text)

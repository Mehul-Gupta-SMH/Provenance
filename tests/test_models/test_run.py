"""Tests for provenance/models/run.py."""
from __future__ import annotations

from provenance.models.run import Run, RunMode, RunStatus


def test_run_defaults():
    run = Run(entity_id=1)

    assert run.status == RunStatus.pending
    assert run.mode == RunMode.isolation
    assert run.experiment_id is None
    assert run.error_message is None


def test_run_status_and_mode_enum_values():
    assert RunStatus.pending == "pending"
    assert RunStatus.running == "running"
    assert RunStatus.completed == "completed"
    assert RunStatus.failed == "failed"
    assert RunMode.isolation == "isolation"
    assert RunMode.aggregate == "aggregate"

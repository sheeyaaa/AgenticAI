from pydantic import ValidationError
import pytest
from prd_agents.blackboard import Blackboard
from prd_agents.models import RequirementPoint


def test_blackboard_validates_and_logs_writes() -> None:
    board = Blackboard()
    board.write("extractor", "requirement_points", [
        RequirementPoint(id="REQ-1", text="A requirement", source_chunk_id="chunk-1")
    ])
    assert board.read("requirement_points")[0].id == "REQ-1"
    assert board.snapshot().write_log[0].version == 1


def test_blackboard_rejects_bad_contract() -> None:
    board = Blackboard()
    with pytest.raises(ValidationError):
        board.write("bad", "requirement_points", [{"id": 3}])

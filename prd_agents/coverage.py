"""Deterministic requirement coverage calculation."""
from .models import CoverageReport, RequirementPoint, TestCase


def check_coverage(requirements: list[RequirementPoint], cases: list[TestCase]) -> CoverageReport:
    requirement_ids = {item.id for item in requirements}
    covered = {req_id for case in cases for req_id in case.req_ids if req_id in requirement_ids}
    positive = {req_id for case in cases if case.type == "positive" for req_id in case.req_ids
                if req_id in requirement_ids}
    negative = {req_id for case in cases if case.type == "negative" for req_id in case.req_ids
                if req_id in requirement_ids}
    edge = {req_id for case in cases if case.type == "edge" for req_id in case.req_ids
            if req_id in requirement_ids}
    invalid = sorted({req_id for case in cases for req_id in case.req_ids
                      if req_id not in requirement_ids})
    behavioral = {
        req_id for case in cases
        if case.actions and case.expected_result.strip()
        for req_id in case.req_ids if req_id in requirement_ids
    }
    uncovered = sorted(requirement_ids - covered)
    missing_positive = sorted(requirement_ids - positive)
    missing_negative = sorted(requirement_ids - negative)
    score = len(covered) / max(1, len(requirement_ids))
    return CoverageReport(
        covered_requirement_ids=sorted(covered),
        uncovered_requirement_ids=uncovered,
        missing_positive_requirement_ids=missing_positive,
        missing_negative_requirement_ids=missing_negative,
        missing_edge_requirement_ids=sorted(requirement_ids - edge),
        invalid_requirement_ids=invalid,
        behaviorally_verified_requirement_ids=sorted(behavioral),
        score=score,
    )

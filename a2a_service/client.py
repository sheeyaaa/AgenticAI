"""ADK-side remote A2A client boundary."""
from __future__ import annotations
from typing import Any
import urllib.request
import json
from prd_agents.models import SeleniumScript


def submit_test_cases(base_url: str, test_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/tasks",
        data=json.dumps({"test_cases": test_cases}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.load(response)
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("A2A service response is missing an artifacts list.")
    return [SeleniumScript.model_validate(item).model_dump(mode="json") for item in artifacts]

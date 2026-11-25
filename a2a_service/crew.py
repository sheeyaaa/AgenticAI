"""CrewAI implementation for the remote Selenium writing stage."""
from __future__ import annotations
import json
from typing import Any
from prd_agents.models import SeleniumScript


def build_crew() -> Any:
    from crewai import Agent, Crew, Process, Task
    writer = Agent(
        role="Selenium Script Writer",
        goal="Create runnable pytest Selenium scripts from typed test cases.",
        backstory="You write clear, robust Python browser tests.",
        verbose=False,
    )
    reviewer = Agent(
        role="Selenium Script Reviewer",
        goal="Review scripts for syntax, locator, and pytest quality problems.",
        backstory="You are a meticulous browser automation reviewer.",
        verbose=False,
    )
    write = Task(description="Write scripts for these test cases: {test_cases}", expected_output="JSON scripts", agent=writer)
    review = Task(description="Review the generated scripts and return corrected JSON: {write}", expected_output="JSON scripts", agent=reviewer)
    return Crew(agents=[writer, reviewer], tasks=[write, review], process=Process.sequential, verbose=False)


def run_crew(test_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = build_crew().kickoff(inputs={"test_cases": json.dumps(test_cases)})
    raw = getattr(result, "raw", str(result))
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("CrewAI reviewer must return a JSON array of Selenium scripts.")
    return [SeleniumScript.model_validate(item).model_dump(mode="json") for item in payload]

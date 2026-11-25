"""Small A2A HTTP facade with an agent card and typed task endpoint."""
from __future__ import annotations
from typing import Any
from fastapi import FastAPI
from pydantic import BaseModel
from prd_agents.models import SeleniumScript, TestCase
from .crew import run_crew

app = FastAPI(title="Selenium Crew A2A Service")


class TaskRequest(BaseModel):
    test_cases: list[TestCase]


@app.get("/.well-known/agent.json")
def agent_card() -> dict[str, Any]:
    return {
        "name": "selenium-script-crew",
        "description": "CrewAI Selenium writer and reviewer",
        "url": "http://127.0.0.1:8081",
        "version": "1.0",
        "capabilities": {"streaming": False},
        "skills": [{"id": "selenium-writing", "name": "Write and review Selenium pytest scripts"}],
    }


@app.post("/tasks")
def task(request: TaskRequest) -> dict[str, Any]:
    artifacts = [
        SeleniumScript.model_validate(item)
        for item in run_crew([case.model_dump(mode="json") for case in request.test_cases])
    ]
    return {"artifacts": [item.model_dump(mode="json") for item in artifacts]}

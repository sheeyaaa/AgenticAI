"""Official MCP FastMCP server exposing deterministic pipeline tools."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field
from prd_agents.coverage import check_coverage
from prd_agents.document import parse_document
from prd_agents.models import RequirementPoint, TestCase, CoverageReport, Locator
from prd_agents.models import SeleniumScript
from prd_agents.pipeline import validate_scripts

mcp = FastMCP("prd-to-selenium")


class ParsedPrdResult(BaseModel):
    source_path: str
    title: str
    sections: list[dict[str, Any]]
    text: str


class LocatorResult(BaseModel):
    valid: bool
    checked: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class LintResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)


@mcp.tool()
def prd_parser_tool(path: str) -> dict[str, Any]:
    result = ParsedPrdResult.model_validate(parse_document(Path(path)).model_dump())
    return result.model_dump()


@mcp.tool()
def coverage_checker_tool(requirements: list[dict[str, Any]], test_cases: list[dict[str, Any]]) -> dict[str, Any]:
    report = check_coverage(
        [RequirementPoint.model_validate(item) for item in requirements],
        [TestCase.model_validate(item) for item in test_cases],
    )
    return CoverageReport.model_validate(report.model_dump()).model_dump()


@mcp.tool()
def selenium_locator_tool(url_or_html: str, locators: list[dict[str, str]]) -> dict[str, Any]:
    """Validate locators using Selenium when a URL is supplied, otherwise HTML parsing."""
    result = LocatorResult(valid=True)
    try:
        if url_or_html.lstrip().startswith("<"):
            from html.parser import HTMLParser
            class Parser(HTMLParser):
                elements: list[tuple[str, dict[str, str], str]] = []
                def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                    self.elements.append(
                        (tag, {key: value or "" for key, value in attrs}, "")
                    )
            parser = Parser()
            parser.feed(url_or_html)
            for raw in locators:
                locator = Locator.model_validate(raw)
                found = _html_locator_exists(parser.elements, locator)
                result.checked.append(locator.value)
                if not found:
                    result.missing.append(locator.value)
        else:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            options = webdriver.ChromeOptions()
            options.add_argument("--headless")
            options.add_argument("--disable-gpu")
            driver = webdriver.Chrome(options=options)
            try:
                driver.get(url_or_html)
                by = {
                    "css selector": By.CSS_SELECTOR, "id": By.ID, "xpath": By.XPATH,
                    "name": By.NAME, "tag name": By.TAG_NAME, "link text": By.LINK_TEXT,
                }
                for raw in locators:
                    locator = Locator.model_validate(raw)
                    driver.find_element(by[locator.strategy], locator.value)
                    result.checked.append(locator.value)
            finally:
                driver.quit()
    except Exception as exc:
        result.valid = False
        result.errors.append(str(exc))
    result.valid = result.valid and not result.missing and not result.errors
    return result.model_dump()


def _html_locator_exists(
    elements: list[tuple[str, dict[str, str], str]], locator: Locator
) -> bool:
    """Validate common generated selectors without starting a browser."""
    if locator.strategy == "id":
        return any(attrs.get("id") == locator.value for _, attrs, _ in elements)
    if locator.strategy == "name":
        return any(attrs.get("name") == locator.value for _, attrs, _ in elements)
    if locator.strategy == "tag name":
        return any(tag == locator.value.lower() for tag, _, _ in elements)
    if locator.strategy == "css selector":
        if locator.value.startswith("#"):
            return _html_locator_exists(
                elements, Locator(strategy="id", value=locator.value[1:])
            )
        if locator.value.startswith("."):
            class_name = locator.value[1:]
            return any(class_name in attrs.get("class", "").split() for _, attrs, _ in elements)
        return any(tag == locator.value.lower() for tag, _, _ in elements)
    return False


@mcp.tool()
def script_linter_tool(code: str) -> dict[str, Any]:
    report = validate_scripts([SeleniumScript(
        test_case_id="MCP", filename="mcp_script.py", code=code,
    )])
    return LintResult(valid=report.valid, errors=report.errors).model_dump()


if __name__ == "__main__":
    mcp.run(transport="stdio")

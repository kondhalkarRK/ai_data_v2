#!/usr/bin/env python3
"""Live chat smoke and evaluation harness against the real HTTP API.

Examples:
    python tests/live_chat_harness.py --smoke
    python tests/live_chat_harness.py --count 50 --output results/live_chat_matrix.json
    python tests/live_chat_harness.py --count 200 --base-url http://127.0.0.1:8123
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import request, error

DEFAULT_BASE_URL = "http://127.0.0.1:8123"
DEFAULT_USERNAME = "admin@askdb.local"
DEFAULT_PASSWORD = "admin123"


def build_opener() -> request.HTTPHandler:
    jar = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar))
    return opener


def api_json(opener, method: str, url: str, payload: dict | None = None) -> tuple[int, dict | list | None, str]:
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=60) as response:
            body = response.read().decode("utf-8")
            try:
                parsed = json.loads(body) if body else None
            except json.JSONDecodeError:
                parsed = body
            return response.status, parsed, body
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body) if body else None
        except json.JSONDecodeError:
            parsed = body
        return exc.code, parsed, body


def login(opener, base_url: str, username: str, password: str) -> tuple[int, dict | list | None]:
    status, payload, _ = api_json(
        opener,
        "POST",
        f"{base_url}/api/v1/auth/login",
        {"username": username, "password": password},
    )
    return status, payload


def ask_chat(opener, base_url: str, question: str) -> tuple[int, dict | list | None, str]:
    return api_json(
        opener,
        "POST",
        f"{base_url}/api/v1/chat/ask-sync",
        {
            "question": question,
            "conversation_id": None,
            "web_retrieval": False,
        },
    )


def generate_question_bank(count: int) -> list[str]:
    stems = [
        "Show {metric} {by}",
        "Compare {metric} {by}",
        "What is the {metric} {by}",
        "Give me the {metric} {by}",
        "Trend of {metric} {by}",
        "Top {n} {dimension} by {metric}",
        "Best performing {dimension} for {metric}",
        "Which {dimension} has the highest {metric}",
        "How many {metric} by {dimension}",
        "Summarize {metric} across {dimension}",
    ]

    metrics = [
        "total sales",
        "revenue",
        "orders",
        "units sold",
        "monthly revenue",
        "annual sales",
        "sales by region",
        "dealer performance",
        "salesperson performance",
        "SUV sales",
        "sedan sales",
        "customer demand",
    ]

    dimensions = [
        "by year",
        "by month",
        "by region",
        "by city",
        "by dealership",
        "by model",
        "by car type",
        "by colour",
        "by salesperson",
        "by dealer grade",
    ]

    filters = [
        "for SUVs",
        "for sedan models",
        "in Mumbai",
        "in Delhi",
        "for Hyundai",
        "for Tata vehicles",
        "for premium cars",
        "in the north region",
        "in the west region",
        "for the last 12 months",
        " for 2024 sales",
        " for the last 3 years",
    ]

    question_bank: list[str] = []
    seen: set[str] = set()
    template_index = 0

    while len(question_bank) < max(1, count):
        template = stems[template_index % len(stems)]
        metric = metrics[(template_index * 2) % len(metrics)]
        dimension = dimensions[(template_index * 3) % len(dimensions)]
        filter_text = filters[(template_index * 5) % len(filters)]

        if template.startswith("Top"):
            q = template.format(n="5", dimension="dealers", metric="revenue")
        elif template.startswith("Best performing"):
            q = template.format(dimension="regions", metric="revenue")
        elif template.startswith("Which"):
            q = template.format(dimension="dealer", metric="sales")
        elif template.startswith("How many"):
            q = template.format(metric="orders", dimension="by region")
        elif template.startswith("Summarize"):
            q = template.format(metric="sales", dimension="by month")
        else:
            q = template.format(metric=metric, by=dimension)

        q = q.strip()
        if q.lower().endswith("by"):
            q = q + " region"

        q = q.replace("  ", " ")
        if q not in seen:
            seen.add(q)
            question_bank.append(q)

        template_index += 1

    # Add a few explicit, human-written variations to keep the matrix grounded and readable.
    explicit = [
        "Show total sales per year",
        "Compare revenue by month",
        "Show dealer performance by region",
        "What are the top 5 dealers by revenue",
        "Show SUV sales by region",
        "Compare SUV sales across regions",
        "Show sales in Mumbai",
        "What is the revenue trend by quarter",
        "Show monthly revenue trend",
        "Compare last 3 months sales for last 3 years",
        "Which city has the highest sales",
        "What is the total order quantity by model",
        "Show top salesperson by revenue",
        "Show total sales by colour",
        "Compare sales by dealer grade",
        "Show sales by car type",
        "Which region has the strongest sales performance",
        "What are the top selling car models",
        "Show revenue by dealership",
        "Which model has the highest units sold",
    ]

    for item in explicit:
        if item not in seen:
            question_bank.append(item)
            seen.add(item)
        if len(question_bank) >= count:
            break

    while len(question_bank) < count:
        candidate = f"Show {metrics[len(question_bank) % len(metrics)]} {dimensions[len(question_bank) % len(dimensions)]}"
        if candidate not in seen:
            question_bank.append(candidate)
            seen.add(candidate)

    return question_bank[:count]


def run_smoke(base_url: str, username: str, password: str) -> dict:
    opener = build_opener()
    status, payload = login(opener, base_url, username, password)
    if status != 200:
        return {
            "ok": False,
            "login_status": status,
            "login_payload": payload,
            "questions": [],
        }

    smoke_questions = [
        "Show total sales per year",
        "Show SUV sales by region",
        "Compare revenue by month",
    ]

    results = []
    for question in smoke_questions:
        chat_status, chat_payload, raw = ask_chat(opener, base_url, question)
        events = chat_payload.get("events", []) if isinstance(chat_payload, dict) else []
        route = None
        a_error = None
        for event in events:
            if isinstance(event, dict):
                if event.get("event") == "stage" and isinstance(event.get("data"), dict):
                    route = event["data"].get("route")
                if event.get("event") == "error":
                    a_error = event.get("data")
        results.append(
            {
                "question": question,
                "status": chat_status,
                "passed": chat_status == 200 and not a_error,
                "route": route,
                "error": a_error,
                "event_count": len(events),
            }
        )

    return {
        "ok": all(item["passed"] for item in results),
        "login_status": status,
        "questions": results,
    }


def run_matrix(base_url: str, username: str, password: str, count: int, output_path: str | None) -> dict:
    opener = build_opener()
    login_status, login_payload = login(opener, base_url, username, password)
    if login_status != 200:
        raise RuntimeError(f"Login failed: status={login_status}, payload={login_payload}")

    bank = generate_question_bank(count)
    rows: list[dict] = []
    for index, question in enumerate(bank, start=1):
        status, payload, raw = ask_chat(opener, base_url, question)
        events = payload.get("events", []) if isinstance(payload, dict) else []
        route = None
        error_code = None
        error_detail = None
        for event in events:
            if not isinstance(event, dict):
                continue
            data = event.get("data")
            if event.get("event") == "stage" and isinstance(data, dict):
                route = data.get("route")
            if event.get("event") == "error" and isinstance(data, dict):
                error_code = data.get("code")
                error_detail = data.get("message")

        passed = status == 200 and error_code is None and len(events) > 0
        rows.append(
            {
                "index": index,
                "question": question,
                "status": status,
                "passed": passed,
                "route": route,
                "error_code": error_code,
                "error_detail": error_detail,
                "event_count": len(events),
            }
        )

    summary = {
        "base_url": base_url,
        "username": username,
        "question_count": len(rows),
        "passed": sum(1 for item in rows if item["passed"]),
        "failed": sum(1 for item in rows if not item["passed"]),
        "questions": rows,
    }

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live AI chat smoke test or evaluation matrix")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API base URL (default: http://127.0.0.1:8123)")
    parser.add_argument("--username", default=DEFAULT_USERNAME, help="API user email / username")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="API password")
    parser.add_argument("--smoke", action="store_true", help="Run a short pass/fail smoke test")
    parser.add_argument("--count", type=int, default=50, help="Number of questions to evaluate in matrix mode")
    parser.add_argument("--output", default=None, help="Optional path for JSON results")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.smoke:
        result = run_smoke(args.base_url, args.username, args.password)
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1

    result = run_matrix(args.base_url, args.username, args.password, args.count, args.output)
    print(
        json.dumps(
            {
                "base_url": result["base_url"],
                "question_count": result["question_count"],
                "passed": result["passed"],
                "failed": result["failed"],
            },
            indent=2,
        )
    )
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

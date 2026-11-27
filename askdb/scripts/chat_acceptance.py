"""Office-only HTTP capture/comparison. Prompts for password; never stores answers/SQL.

Uses the real authenticated ask-sync endpoint. Questions can consume quota/model
tokens and report questions create unsaved application reports. No automatic rollout.
"""

import argparse
import getpass
import hashlib
import ipaddress
import json
import math
import re
import statistics
import time
from decimal import Decimal, InvalidOperation
from http.cookiejar import CookieJar
from pathlib import Path
from urllib import error, parse, request


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def validate_url(value):
    url = parse.urlsplit(value)
    if url.username or url.password or url.query or url.fragment or not url.hostname:
        raise ValueError("Use an API base URL without credentials, query or fragment.")
    local = url.hostname == "localhost"
    try:
        local |= ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        pass
    if url.scheme != "https" and not (url.scheme == "http" and local):
        raise ValueError("Remote APIs require HTTPS; local loopback HTTP is supported.")
    return value.rstrip("/")


def equal(actual, expected):
    if isinstance(expected, bool) or expected is None:
        return actual is expected
    if isinstance(expected, (int, float)):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isfinite(actual)
            and math.isfinite(expected)
            and math.isclose(actual, expected, rel_tol=0, abs_tol=1e-6)
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(equal(a, b) for a, b in zip(actual, expected, strict=True))
        )
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and equal(actual[key], val) for key, val in expected.items()
        )
    return actual == expected


def _inspect_flat(events, expected=None):
    """Score route and numerical result independently. Missing gold is unreviewed."""
    meta = next((e["data"] for e in events if e["event"] == "meta"), {})
    rows = next((e["data"].get("rows", []) for e in events if e["event"] == "rows"), [])
    columns = next(
        (e["data"].get("columns", []) for e in events if e["event"] == "columns"), []
    )
    text = "".join(e["data"].get("token", "") for e in events if e["event"] == "token")
    route = (
        meta.get("requestedOutcome")
        or (meta.get("typedRequest") or {}).get("outcome")
        or meta.get("route")
        or meta.get("responseKind")
    )
    route = {"sql": "analytics", "knowledge": "documents"}.get(route, route)
    runtime = meta.get("llmRuntime") or {}
    result = {
        "mode": meta.get("executionMode"),
        "route": route,
        "responseKind": meta.get("responseKind"),
        "rowCount": len(rows),
        "cacheHit": meta.get("cacheHit"),
        "resultHash": digest({"columns": columns, "rows": rows}),
        "dataAsOf": meta.get("dataAsOf"),
        "model": runtime.get("model") if runtime.get("invoked") else None,
        "configuredModel": runtime.get("configuredModel"),
        "usage": meta.get("runUsage"),
        "responseId": next(
            (e["data"].get("historyId") for e in events if e["event"] == "done"), None
        ),
        "narrativeHash": digest(text),
        "resultCorrect": None,
        "narrationCorrect": None,
        "routeCorrect": None,
        "answerCorrect": None,
        "review": "unreviewed",
    }
    if expected:
        if "route" in expected:
            result["routeCorrect"] = route == expected["route"]
        checks = []
        for key, actual in (
            ("rows", rows),
            ("columns", columns),
            ("responseKind", meta.get("responseKind")),
        ):
            if key in expected:
                checks.append(equal(actual, expected[key]))
        if "textContains" in expected:
            checks.append(
                all(
                    term.casefold() in text.casefold()
                    for term in expected["textContains"]
                )
            )
        complete = (
            ("rows" in expected and "columns" in expected)
            if route in {"analytics", "investigation"}
            else bool(expected.get("textContains"))
        )
        if "text" in expected:
            result["narrationCorrect"] = text.strip() == expected["text"].strip()
            checks.append(result["narrationCorrect"])
            complete = complete or route not in {"analytics", "investigation"}
        if route == "report":
            complete = False  # Panel evidence needs manual review in Builder.
        if checks:
            result["resultCorrect"] = all(checks) if complete else None
        result["answerCorrect"] = (
            False
            if result["resultCorrect"] is False or result["narrationCorrect"] is False
            else True
            if result["resultCorrect"] is True and result["narrationCorrect"] is True
            else None
        )
        result["review"] = (
            "passed"
            if result["routeCorrect"] is True and result["answerCorrect"] is True
            else "failed"
            if False in (result["routeCorrect"], result["answerCorrect"])
            else "incomplete_gold"
        )
    if any(e["event"] in {"error", "cancelled"} for e in events):
        result["review"] = "failed"
    return result


def _exact(actual, expected):
    """Reference structures must cover every returned field, including empty lists."""
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(_exact(actual[k], v) for k, v in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_exact(a, b) for a, b in zip(actual, expected, strict=True))
        )
    return equal(actual, expected)


def _reference_rows(actual, expected, columns, numeric_columns, order):
    if order not in {"ordered", "unordered"} or len(actual) != len(expected):
        return False

    def row_equal(left, right):
        if set(left) != set(columns) or set(right) != set(columns):
            return False
        for key in columns:
            a, b = left[key], right[key]
            if key in numeric_columns and (isinstance(a, bool) or isinstance(b, bool)):
                return False
            if a is None or b is None or isinstance(a, bool) or isinstance(b, bool):
                if a is not b:
                    return False
            elif key in numeric_columns:
                try:
                    first, second = Decimal(str(a)), Decimal(str(b))
                    if not first.is_finite() or not second.is_finite():
                        return False
                    if (
                        isinstance(numeric_columns, dict)
                        and numeric_columns[key] == "integer"
                        and (first != first.to_integral_value() or first != second)
                    ):
                        return False
                    if abs(first - second) > Decimal("0.000001"):
                        return False
                except InvalidOperation:
                    return False
            elif not _exact(a, b):
                return False
        return True

    remaining = list(expected)
    for row in actual:
        if order == "ordered":
            if not row_equal(row, remaining.pop(0)):
                return False
        else:
            match = next(
                (i for i, ref in enumerate(remaining) if row_equal(row, ref)), None
            )
            if match is None:
                return False
            remaining.pop(
                match
            )  # Preserve duplicate multiplicity; do not compare sets.
    return True


def _analysis_projection(meta):
    """In-memory evidence only. Never write this projection or its rows to a capture."""
    execution = meta.get("analyticalExecution") or {}
    plan = meta.get("analyticalPlan") or {}
    view = meta.get("analyticalPresentation") or {}
    if view.get("version") != 1 or view.get("status") != execution.get("status"):
        raise ValueError("Display state does not match execution")
    if view.get("scope") != execution.get("scope_labels"):
        raise ValueError("Displayed scope does not match execution")
    ids = [step["id"] for step in plan.get("steps", [])]
    if len(set(ids)) != len(ids) or len(ids) != len(execution.get("steps", [])):
        raise ValueError("Missing or duplicate analysis step")
    result = []
    numeric = []
    for index, definition in enumerate(plan.get("steps", [])):
        observed = execution["steps"][index]
        shown = view["steps"][index]
        if observed["id"] != ids[index] or shown["id"] != ids[index]:
            raise ValueError("Step identities do not match")
        if (
            shown.get("status") != observed.get("status")
            or shown.get("verified") != observed.get("verified")
            or [c["key"] for c in shown.get("columns", [])] != observed["columns"]
            or shown.get("displayedRows") != len(observed["rows"])
        ):
            raise ValueError("Displayed step does not match execution")
        req = definition["request"]
        result.append(
            {
                "operation": definition["operation"],
                "dependsOn": [
                    ids.index(parent) for parent in definition.get("depends_on", [])
                ],
                "measures": [m["id"] for m in req["measures"]],
                "grouping": req.get("group_by", []),
                "filters": [
                    {k: f[k] for k in ("field", "operator", "values")}
                    for f in shown.get("filters", [])
                ],
                "period": {
                    k: shown["searchPeriod"].get(k) for k in ("start", "endExclusive")
                },
                "comparisonPeriods": shown.get("comparisonPeriods", []),
                "baseline": (shown.get("baseline") or {}).get("kind"),
                "status": observed["status"],
                "verified": observed["verified"],
                "columns": observed["columns"],
                "rows": observed["rows"],
                "totalGroups": observed["total_groups"],
                "selectedGroups": observed["selected_groups"],
            }
        )
        numeric.append(
            {
                o["name"]: o["value_type"]
                for o in definition["outputs"]
                if o["value_type"] in {"integer", "decimal"}
            }
        )
    return {
        "status": execution["status"],
        "scope": view["scope"],
        "steps": result,
        "checks": [
            {
                "headlineStep": ids.index(c["headlineStep"]),
                "contributorStep": ids.index(c["contributorStep"]),
                "measure": c["measure"],
                "passed": c["passed"],
            }
            for c in execution.get("checks", [])
        ],
        "unanswered": [
            {"status": u["status"], "reason": u["reason"]}
            for u in view.get("unanswered", [])
        ],
    }, numeric


def _human_reference(expected):
    ref = expected.get("reference") or {}
    if not isinstance(ref, dict):
        return False
    fingerprint = ref.get("sqlSha256", "")
    return bool(
        ref.get("reviewer")
        and ref.get("datasetRevision")
        and ref.get("reviewedAt")
        and ref.get("kind") == "human_reference"
        and isinstance(ref.get("holdout"), bool)
        and isinstance(fingerprint, str)
        and len(fingerprint) == 64
        and all(c in "0123456789abcdef" for c in fingerprint)
    )


def inspect(events, expected=None):
    """Score complete dependent evidence; flat Chat retains its existing evaluator."""
    meta = next((e["data"] for e in events if e["event"] == "meta"), {})
    expected = expected or {}
    execution = meta.get("analyticalExecution") or {}
    if (
        not execution
        or execution.get("status") in {"denied", "failed", "cancelled", "disabled"}
    ) and "analysis" not in expected:
        result = _inspect_flat(events, expected)
    else:
        result = _inspect_flat(
            events,
            {
                k: v
                for k, v in expected.items()
                if k in {"route", "text", "textContains"}
            },
        )
        result.update(
            resultCorrect=None,
            coverageCorrect=None,
            answerCorrect=None,
            referenceReviewed=_human_reference(expected),
            review="incomplete_gold",
        )
        gold = expected.get("analysis")
        try:
            actual, numeric = _analysis_projection(meta)
            result["resultHash"] = digest(actual)
            result["stepCount"] = len(actual["steps"])
            if gold:
                structure = {
                    "operation",
                    "dependsOn",
                    "measures",
                    "grouping",
                    "filters",
                    "period",
                    "comparisonPeriods",
                    "baseline",
                }
                data = {
                    "status",
                    "verified",
                    "columns",
                    "rows",
                    "totalGroups",
                    "selectedGroups",
                }
                complete = set(gold) == {
                    "status",
                    "scope",
                    "steps",
                    "checks",
                    "unanswered",
                }
                refs = gold.get("steps", [])
                complete &= len(refs) == len(actual["steps"]) and bool(refs)
                coverage, values = [], []
                for index, ref in enumerate(refs):
                    if index >= len(actual["steps"]):
                        coverage.append(False)
                        continue
                    obs = actual["steps"][index]
                    complete &= set(ref) == structure | data | {"rowOrder"}
                    coverage.extend(
                        _exact(obs[k], ref[k]) for k in structure if k in ref
                    )
                    values.extend(
                        _exact(obs[k], ref[k]) for k in data - {"rows"} if k in ref
                    )
                    if "rows" in ref and "columns" in ref:
                        values.append(
                            _reference_rows(
                                obs["rows"],
                                ref["rows"],
                                ref["columns"],
                                numeric[index],
                                ref.get("rowOrder"),
                            )
                        )
                coverage.extend(
                    _exact(actual[k], gold[k])
                    for k in ("status", "scope", "checks", "unanswered")
                    if k in gold
                )
                if len(refs) != len(actual["steps"]):
                    coverage.append(False)
                result["coverageCorrect"] = (
                    all(coverage) if complete else False if False in coverage else None
                )
                result["resultCorrect"] = (
                    all(values) if complete else False if False in values else None
                )
                checks = [
                    result["resultCorrect"],
                    result["coverageCorrect"],
                    result["narrationCorrect"],
                ]
                result["answerCorrect"] = (
                    False
                    if False in checks
                    else True
                    if all(c is True for c in checks)
                    else None
                )
            text = "".join(
                e["data"].get("token", "") for e in events if e["event"] == "token"
            )
            view = meta["analyticalPresentation"]
            display_text = [view.get("summary", ""), *view.get("notes", [])]
            for shown in view["steps"]:
                display_text.extend([shown.get("summary", ""), *shown.get("notes", [])])
            if any(part.strip() and part.strip() not in text for part in display_text):
                result.update(narrationCorrect=False, answerCorrect=False)
            if False in (result["routeCorrect"], result["answerCorrect"]):
                result["review"] = "failed"
            elif (
                result["routeCorrect"] is True
                and result["answerCorrect"] is True
                and result["referenceReviewed"]
            ):
                result["review"] = "passed"
        except (KeyError, ValueError, TypeError, IndexError):
            result.update(
                resultCorrect=False,
                coverageCorrect=False,
                answerCorrect=False,
                review="failed",
                failureCode="analysis_evidence_missing_or_invalid",
            )
    usage = result.get("usage") or {}
    calls = [
        usage.get(k)
        for k in ("initialModelCalls", "verificationModelCalls", "correctionModelCalls")
    ]
    result["budgetCorrect"] = (
        sum(calls) <= 2 if all(type(c) is int and c >= 0 for c in calls) else None
    )
    if result.get("route") == "report":
        result["budgetCorrect"] = None  # AskBI has its own separately approved budget.
    if (
        "analysis" in expected
        and result["review"] == "passed"
        and result["budgetCorrect"] is None
    ):
        result["review"] = "incomplete_usage"
    if result["budgetCorrect"] is False or any(
        e["event"] in {"error", "cancelled"} for e in events
    ):
        result["review"] = "failed"
    if meta.get("responseKind") in {"denied", "cancelled", "failed"} and (
        execution.get("sql")
        or any(s.get("rows") for s in execution.get("steps", []))
        or any(
            e["event"] == "sql" or e["event"] == "rows" and e["data"].get("rows")
            for e in events
        )
    ):
        result.update(review="failed", failureCode="terminal_response_exposed_evidence")
    result["dependentObserved"] = bool(meta.get("analyticalExecution"))
    result["analysisExpected"] = "analysis" in expected
    # Only established counters/flags survive; no provider error/prompt extension fields.
    if result.get("usage") is not None:
        result["usage"] = {
            k: v
            for k, v in usage.items()
            if k
            in {
                "initialModelCalls",
                "verificationModelCalls",
                "correctionModelCalls",
                "inputTokens",
                "outputTokens",
                "tokensEstimated",
                "modelUsageComplete",
                "initialInputTokens",
                "initialOutputTokens",
                "verificationInputTokens",
                "verificationOutputTokens",
                "interpretationMs",
                "planningMs",
                "executionMs",
                "narrationMs",
                "analyticalQueries",
                "warehouseQueries",
                "cacheHit",
            }
            and isinstance(v, (int, float, bool))
            and (not isinstance(v, float) or math.isfinite(v))
        }
        models = usage.get("modelsUsed")
        if (
            isinstance(models, list)
            and len(models) <= 2
            and all(isinstance(m, str) and len(m) <= 256 for m in models)
        ):
            result["usage"]["modelsUsed"] = models
    return result


def summarize(cases):
    """Unknown and failed are distinct; latency is not an answer-quality score."""
    scores = {}
    for key in (
        "routeCorrect",
        "coverageCorrect",
        "resultCorrect",
        "narrationCorrect",
        "budgetCorrect",
    ):
        scores[key] = {
            "passed": sum(c.get(key) is True for c in cases),
            "failed": sum(c.get(key) is False for c in cases),
            "unknown": sum(c.get(key) is None for c in cases),
        }
    timings = sorted(
        c["latencyMs"] for c in cases if type(c.get("latencyMs")) in {int, float}
    )
    return {
        "cases": len(cases),
        "checks": scores,
        "fullyPassed": sum(c.get("review") == "passed" for c in cases),
        "medianLatencyMs": statistics.median(timings) if timings else None,
        "p95LatencyMs": timings[math.ceil(0.95 * len(timings)) - 1]
        if timings
        else None,
        "p95Method": "nearest rank",
        "rolloutApproved": False,
    }


def validate_inputs(cases, gold, revision=None):
    """Offline preflight. Reviewer declarations do not independently prove authorship."""
    if not isinstance(cases, list) or not 1 <= len(cases) <= 100:
        raise ValueError("Use 1-100 cases")
    if any(
        not isinstance(c, dict)
        or not isinstance(c.get("id"), str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", c["id"])
        or not isinstance(c.get("question"), str)
        or not 1 <= len(c["question"].strip()) <= 4000
        for c in cases
    ) or len({c["id"] for c in cases}) != len(cases):
        raise ValueError(
            "Cases require unique IDs and nonempty questions up to 4000 characters"
        )
    if not isinstance(gold, dict) or not set(gold) <= {c["id"] for c in cases}:
        raise ValueError("Reference IDs must belong to the case file")
    dependent, holdouts = 0, 0
    routes = {c["id"]: c.get("route") for c in cases}
    for case_id, reference in gold.items():
        if not isinstance(reference, dict):
            raise TypeError("Reference answers must be objects")
        if (
            routes[case_id]
            and reference.get("route")
            and routes[case_id] != reference["route"]
        ):
            raise ValueError("Case and reference routes disagree")
        if "analysis" not in reference:
            continue
        dependent += 1
        if not _human_reference(reference) or not isinstance(
            reference.get("text"), str
        ):
            raise ValueError(
                "Dependent references require reviewer provenance and approved narration"
            )
        if not revision or reference["reference"]["datasetRevision"] != revision:
            raise ValueError(
                "Dependent references require the matching frozen warehouse revision"
            )
        holdouts += reference["reference"]["holdout"]
        analysis = reference["analysis"]
        if set(analysis) != {"status", "scope", "steps", "checks", "unanswered"}:
            raise ValueError(
                "Reference must cover status, scope, steps, checks and unanswered parts"
            )
        if not 1 <= len(analysis["steps"]) <= 4:
            raise ValueError("Dependent references require one to four steps")
        required = {
            "operation",
            "dependsOn",
            "measures",
            "grouping",
            "filters",
            "period",
            "comparisonPeriods",
            "baseline",
            "status",
            "verified",
            "columns",
            "rows",
            "totalGroups",
            "selectedGroups",
            "rowOrder",
        }
        for index, step in enumerate(analysis["steps"]):
            if set(step) != required or step["rowOrder"] not in {
                "ordered",
                "unordered",
            }:
                raise ValueError(
                    "Reference step must cover every structural and result field"
                )
            if len(step["rows"]) > 50 or any(
                type(d) is not int or not 0 <= d < index for d in step["dependsOn"]
            ):
                raise ValueError(
                    "Reference steps must respect row caps and ordered dependencies"
                )
            if any(set(row) != set(step["columns"]) for row in step["rows"]):
                raise ValueError(
                    "Reference rows must include all declared columns exactly"
                )
    return {
        "inputValidationOnly": True,
        "cases": len(cases),
        "references": len(gold),
        "dependentReferences": dependent,
        "holdoutsDeclaredByReviewer": holdouts,
        "missingReferences": len(cases) - len(gold),
        "rolloutApproved": False,
    }


def compare(before, after):
    keys = ("caseHash", "datasetLabel", "expectedModel", "goldHash", "principalHash")
    if (
        not before.get("principalHash")
        or any(before.get(key) != after.get(key) for key in keys)
        or not before.get("datasetLabel")
    ):
        raise ValueError(
            "Cases, dataset label, expected model and gold file must match."
        )
    dependent_pair = (before.get("label"), after.get("label")) == (
        "typed-baseline",
        "dependent",
    )
    if not dependent_pair and (before.get("label"), after.get("label")) != (
        "legacy",
        "typed",
    ):
        raise ValueError("Compare legacy/typed or typed-baseline/dependent captures.")
    if dependent_pair and (
        not before.get("warehouseRevision")
        or before.get("warehouseRevision") != after.get("warehouseRevision")
    ):
        raise ValueError(
            "Dependent comparisons require the same frozen warehouse revision."
        )
    output = []
    old = {row["id"]: row for row in before["cases"]}
    if set(old) != {row["id"] for row in after["cases"]}:
        raise ValueError("Missing paired cases")
    for row in after["cases"]:
        previous = old.get(row["id"])
        if not previous:
            raise ValueError("Missing paired case")
        comparable = (
            previous.get("mode") == ("typed" if dependent_pair else "legacy")
            and row.get("mode") == "typed"
            and previous.get("dataAsOf") == row.get("dataAsOf")
        )
        for observed in (previous, row):
            if observed.get("model") and observed["model"] != after["expectedModel"]:
                comparable = False
            if observed.get("configuredModel") != after["expectedModel"]:
                comparable = False
        comparable = comparable and not (
            previous.get("cacheHit") or row.get("cacheHit")
        )
        if dependent_pair and (
            previous.get("dependentObserved")
            or row.get("analysisExpected")
            and not row.get("dependentObserved")
        ):
            comparable = False
        if dependent_pair:
            for observed in (previous, row):
                usage = observed.get("usage") or {}
                counts = [
                    usage.get(k)
                    for k in (
                        "initialModelCalls",
                        "verificationModelCalls",
                        "correctionModelCalls",
                    )
                ]
                models = usage.get("modelsUsed")
                if (
                    usage.get("modelUsageComplete") is not True
                    or not isinstance(models, list)
                    or not all(type(c) is int and c >= 0 for c in counts)
                    or len(models) != sum(counts)
                    or any(m != after["expectedModel"] for m in models)
                ):
                    comparable = False
        output.append(
            {
                "id": row["id"],
                "comparable": comparable,
                "costComparable": comparable
                and previous.get("usage") is not None
                and row.get("usage") is not None,
                "performanceComparable": comparable
                and previous["review"] == "passed"
                and row["review"] == "passed",
                "legacyReview": previous["review"],
                "typedReview": row["review"],
                "legacyLatencyMs": previous.get("latencyMs"),
                "typedLatencyMs": row.get("latencyMs"),
                "legacyUsage": previous.get("usage"),
                "typedUsage": row.get("usage"),
            }
        )
    return {
        "comparison": "typed-baseline/dependent" if dependent_pair else "legacy/typed",
        "pairs": output,
        "rolloutApproved": False,
        "note": "Warehouse revisions are operator attestations, not automatic snapshot proof. Freeze the warehouse and review correctness/UI independently. Missing usage stays unknown. Legacy-prefixed pair fields describe the baseline capture.",
    }


def capture(args):
    base = validate_url(args.base_url)
    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8")) if args.gold else {}
    validate_inputs(cases, gold, getattr(args, "warehouse_revision", None))
    jar = CookieJar()
    opener = request.build_opener(request.HTTPCookieProcessor(jar), NoRedirect())

    def post(path, body):
        csrf = next((c.value for c in jar if c.name == "nql_csrf"), "")
        req = request.Request(
            base + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Industry": "automotive",
                args.csrf_header: csrf,
            },
        )
        with opener.open(req, timeout=180) as response:
            return json.load(response)

    session = post(
        "/api/v1/auth/login",
        {
            "username": args.username,
            "password": getpass.getpass("Application password (not saved): "),
        },
    )
    output = {
        "principalHash": digest(
            {key: session["user"].get(key) for key in ("id", "role", "regionAccess")}
        ),
        "label": args.mode,
        "warehouseRevision": getattr(args, "warehouse_revision", None),
        "datasetLabel": args.dataset_label,
        "expectedModel": args.expected_model,
        "caseHash": digest(cases),
        "goldHash": digest(gold),
        "cases": [],
    }
    conversations = {}
    for case in cases:
        started = time.perf_counter()
        group = case.get("conversation", case["id"])
        try:
            payload = post(
                "/api/v1/chat/ask-sync",
                {
                    "question": case["question"],
                    "conversationId": conversations.get(group),
                    "webRetrieval": False,
                    "useDocuments": False,
                },
            )
            events = payload["events"]
            expected = {"route": case["route"]} if case.get("route") else {}
            expected.update(gold.get(case["id"]) or {})
            row = inspect(events, expected)
            for event in events:
                if event["event"] == "done" and event["data"].get("conversationId"):
                    conversations[group] = event["data"]["conversationId"]
            row.update(
                id=case["id"],
                latencyMs=round((time.perf_counter() - started) * 1000, 2),
            )
        except (error.URLError, KeyError, ValueError):
            row = {"id": case["id"], "review": "transport_failed"}
        output["cases"].append(row)
        print(case["id"], row["review"])
        # Persist progress without passwords, cookies, prompts, SQL or result rows.
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    timings = [row["latencyMs"] for row in output["cases"] if "latencyMs" in row]
    output["summary"] = summarize(output["cases"])
    Path(args.output).write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(
        "Completed",
        len(cases),
        "cases; median HTTP latency ms:",
        statistics.median(timings) if timings else "unknown",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("capture")
    for key in (
        "base-url",
        "username",
        "mode",
        "dataset-label",
        "expected-model",
        "cases",
        "output",
    ):
        live.add_argument("--" + key, required=True)
    live.add_argument("--gold")
    live.add_argument("--warehouse-revision")
    live.add_argument("--csrf-header", default="X-CSRF-Token")
    paired = sub.add_parser("compare")
    paired.add_argument("--legacy", required=True)
    paired.add_argument("--typed", required=True)
    paired.add_argument("--output", required=True)
    preflight = sub.add_parser(
        "validate", help="Check private references without network/model calls"
    )
    preflight.add_argument("--cases", required=True)
    preflight.add_argument("--gold", required=True)
    preflight.add_argument("--warehouse-revision")
    args = parser.parse_args()
    try:
        if args.command == "capture":
            if args.mode not in {"legacy", "typed", "typed-baseline", "dependent"}:
                raise ValueError("Mode is legacy, typed, typed-baseline or dependent")
            if (
                args.mode in {"typed-baseline", "dependent"}
                and not args.warehouse_revision
            ):
                raise ValueError(
                    "Supply the frozen warehouse revision for dependent acceptance"
                )
            capture(args)
        elif args.command == "validate":
            print(
                json.dumps(
                    validate_inputs(
                        json.loads(Path(args.cases).read_text(encoding="utf-8")),
                        json.loads(Path(args.gold).read_text(encoding="utf-8")),
                        args.warehouse_revision,
                    ),
                    indent=2,
                )
            )
        else:
            report = compare(
                json.loads(Path(args.legacy).read_text()),
                json.loads(Path(args.typed).read_text()),
            )
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    except (ValueError, KeyError, TypeError, error.URLError, OSError):
        parser.exit(
            1,
            "Acceptance run could not complete. Check API availability, login, paths and options; no raw server errors are printed.\n",
        )


if __name__ == "__main__":
    main()

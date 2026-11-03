#!/usr/bin/env python3
"""Offline filing-review calculations; Python 3.10+, standard library only."""
import argparse
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json
from pathlib import Path
import re
import sys


class InputError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise InputError(message)


def obj(value, required, optional=(), label="object"):
    require(isinstance(value, dict), f"{label}: expected object")
    require(set(required) <= value.keys(), f"{label}: missing fields {set(required) - value.keys()}")
    require(value.keys() <= set(required) | set(optional), f"{label}: unexpected fields {value.keys() - set(required) - set(optional)}")


def text(value, label):
    require(isinstance(value, str) and bool(value.strip()), f"{label}: expected nonempty string")
    return value


def array(value, label):
    require(isinstance(value, list), f"{label}: expected list")
    return value


def strings(value, label):
    array(value, label)
    for item in value:
        text(item, label)
    require(len(value) == len(set(value)), f"{label}: duplicate value")
    return value


def evidence(value, label):
    strings(value, label)
    require(bool(value), f"{label}: provide at least one source locator")


def number(value, label, nonnegative=True):
    require(isinstance(value, (str, int)) and not isinstance(value, bool), f"{label}: use a decimal string or integer")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise InputError(f"{label}: invalid decimal") from None
    require(result.is_finite(), f"{label}: must be finite")
    require(abs(result) <= Decimal("1000000000000"), f"{label}: exceeds supported magnitude")
    require(not nonnegative or result >= 0, f"{label}: cannot be negative")
    return result


def money(value, label):
    result = number(value, label)
    require(result == result.quantize(Decimal("0.01")), f"{label}: at most two fractional digits")
    return result


def day(value, label):
    text(value, label)
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, f"{label}: expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError(f"{label}: invalid date") from None


def indexed(items, label):
    array(items, label)
    result = {}
    for item in items:
        require(isinstance(item, dict) and "id" in item, f"{label}: each record needs an id")
        ident = text(item["id"], label + ".id")
        require(ident not in result, f"{label}: duplicate id {ident}")
        result[ident] = item
    return result


def fmt(value):
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def validate(data):
    obj(data, ["schema_version", "policy", "strategy", "inventions", "portfolio", "cost_catalog", "budget", "plan", "scenarios"])
    require(data["schema_version"] == "1.0", "Unsupported schema_version")
    policy = data["policy"]
    obj(policy, ["id", "state", "criteria", "business_threshold"], ["approved_by", "approved_on"], "policy")
    text(policy["id"], "policy.id")
    require(policy["state"] in ("draft", "approved"), "policy.state: draft or approved")
    if policy["state"] == "approved":
        text(policy.get("approved_by"), "policy.approved_by")
        day(policy.get("approved_on"), "policy.approved_on")
    threshold = number(policy["business_threshold"], "business_threshold")
    require(threshold <= 100, "business_threshold: must be 0..100")
    criteria = indexed(policy["criteria"], "criteria")
    require(bool(criteria), "At least one criterion is required")
    for c in criteria.values():
        obj(c, ["id", "description", "weight", "min", "max"], label="criterion")
        text(c["description"], "criterion.description")
        require(number(c["weight"], "weight") > 0, "weight: must be positive")
        require(number(c["max"], "max", False) > number(c["min"], "min", False), "max must exceed min")
    strategy = data["strategy"]
    obj(strategy, ["buckets", "gaps"], label="strategy")
    buckets = indexed(strategy["buckets"], "buckets")
    for b in buckets.values():
        obj(b, ["id", "name", "team", "source_refs"], label="bucket")
        text(b["name"], "bucket.name")
        text(b["team"], "bucket.team")
        evidence(b["source_refs"], "bucket.source_refs")
    gaps = indexed(strategy["gaps"], "gaps")
    for g in gaps.values():
        obj(g, ["id", "bucket_id", "description", "source_refs"], label="gap")
        require(g["bucket_id"] in buckets, "gap: unknown bucket")
        text(g["description"], "gap.description")
        evidence(g["source_refs"], "gap.source_refs")
    inventions = indexed(data["inventions"], "inventions")
    for inv in inventions.values():
        obj(inv, ["id", "title", "bucket_ids", "technical_terms", "gap_ids", "source_refs", "ratings"], label="invention")
        text(inv["title"], "invention.title")
        evidence(inv["source_refs"], "invention.source_refs")
        require(set(strings(inv["bucket_ids"], "bucket_ids")) <= buckets.keys(), "invention: unknown bucket")
        strings(inv["technical_terms"], "technical_terms")
        require(set(strings(inv["gap_ids"], "gap_ids")) <= gaps.keys(), "invention: unknown gap")
        for gid in inv["gap_ids"]:
            require(gaps[gid]["bucket_id"] in inv["bucket_ids"], "invention gap must belong to an assigned bucket")
        require(isinstance(inv["ratings"], dict), "ratings: expected object")
        require(inv["ratings"].keys() <= criteria.keys(), "ratings: unknown criterion")
        for cid, rating in inv["ratings"].items():
            obj(rating, ["value", "rationale", "source_refs"], label="rating")
            text(rating["rationale"], "rating.rationale")
            strings(rating["source_refs"], "rating.source_refs")
            if rating["value"] is not None:
                value = number(rating["value"], "rating.value", False)
                require(number(criteria[cid]["min"], "min", False) <= value <= number(criteria[cid]["max"], "max", False), "rating: outside configured scale")
                evidence(rating["source_refs"], "rated value source_refs")
    portfolio = indexed(data["portfolio"], "portfolio")
    for rec in portfolio.values():
        obj(rec, ["id", "title", "family_id", "jurisdiction", "status", "status_as_of", "bucket_ids", "technical_terms", "claim_refs", "source_refs"], label="portfolio record")
        for key in ("title", "jurisdiction"):
            text(rec[key], key)
        if rec["family_id"] is not None:
            text(rec["family_id"], "family_id")
        require(rec["status"] in ("pending", "issued", "expired", "abandoned", "unknown"), "portfolio: unsupported status")
        if rec["status_as_of"] is not None:
            day(rec["status_as_of"], "status_as_of")
        require(set(strings(rec["bucket_ids"], "portfolio.bucket_ids")) <= buckets.keys(), "portfolio: unknown bucket")
        strings(rec["technical_terms"], "portfolio.technical_terms")
        strings(rec["claim_refs"], "claim_refs")
        evidence(rec["source_refs"], "portfolio.source_refs")
    cat = data["cost_catalog"]
    obj(cat, ["currency", "items"], label="cost_catalog")
    require(isinstance(cat["currency"], str) and re.fullmatch(r"[A-Z]{3}", cat["currency"]) is not None, "currency: expected uppercase three-letter code")
    costs = indexed(cat["items"], "cost items")
    for item in costs.values():
        obj(item, ["id", "description", "unit_cost", "source_refs"], label="cost item")
        text(item["description"], "cost description")
        money(item["unit_cost"], "unit_cost")
        evidence(item["source_refs"], "cost.source_refs")
    budget = data["budget"]
    obj(budget, ["currency", "start", "end", "limit", "spent", "committed", "contingency_percent", "source_refs"], label="budget")
    require(budget["currency"] == cat["currency"], "Mixed currencies are not supported")
    require(day(budget["start"], "budget.start") <= day(budget["end"], "budget.end"), "budget.start must not follow end")
    for key in ("limit", "spent", "committed"):
        money(budget[key], "budget." + key)
    require(number(budget["contingency_percent"], "contingency_percent") <= 100, "contingency_percent: expected 0..100")
    evidence(budget["source_refs"], "budget.source_refs")
    plan = indexed(data["plan"], "plan")
    for line in plan.values():
        obj(line, ["id", "invention_id", "cost_id", "quantity", "expected_date", "source_refs"], label="plan line")
        require(line["invention_id"] in inventions, "plan: unknown invention")
        require(line["cost_id"] in costs, "plan: unknown cost item")
        require(type(line["quantity"]) is int and 0 < line["quantity"] <= 1000000, "quantity: expected positive integer <= 1000000")
        day(line["expected_date"], "expected_date")
        evidence(line["source_refs"], "plan.source_refs")
    scenarios = indexed(data["scenarios"], "scenarios")
    require(bool(scenarios), "At least one explicit scenario is required")
    for scenario in scenarios.values():
        obj(scenario, ["id", "description", "plan_line_ids"], label="scenario")
        text(scenario["description"], "scenario.description")
        require(set(strings(scenario["plan_line_ids"], "plan_line_ids")) <= plan.keys(), "scenario: unknown plan line")
    return criteria, buckets, gaps, inventions, portfolio, costs, plan


def evaluate(data):
    criteria, buckets, gaps, inventions, portfolio, costs, plan = validate(data)
    policy = data["policy"]
    total_weight = sum(number(c["weight"], "weight") for c in criteria.values())
    reviews = []
    for inv in inventions.values():
        missing, contributions = [], []
        weighted = Decimal(0)
        for cid, c in criteria.items():
            r = inv["ratings"].get(cid)
            if r is None or r["value"] is None:
                missing.append(cid)
                continue
            normalized = (number(r["value"], "value", False) - number(c["min"], "min", False)) / (number(c["max"], "max", False) - number(c["min"], "min", False)) * 100
            contribution = normalized * number(c["weight"], "weight") / total_weight
            weighted += contribution
            contributions.append({"criterion_id": cid, "value": r["value"], "normalized_score": fmt(normalized), "weighted_points": fmt(contribution), "rationale": r["rationale"], "source_refs": r["source_refs"]})
        # Compare the unrounded result; display rounding cannot move a case over a threshold.
        threshold_result = None if missing or policy["state"] != "approved" else weighted >= number(policy["business_threshold"], "threshold")
        candidates = []
        inv_terms = {t.strip().casefold() for t in inv["technical_terms"]}
        for rec in portfolio.values():
            common_buckets = sorted(set(inv["bucket_ids"]) & set(rec["bucket_ids"]))
            common_terms = sorted(inv_terms & {t.strip().casefold() for t in rec["technical_terms"]})
            if common_buckets or common_terms:
                candidates.append({"record_id": rec["id"], "family_id": rec["family_id"], "status": rec["status"], "status_as_of": rec["status_as_of"], "jurisdiction": rec["jurisdiction"], "shared_buckets": common_buckets, "shared_terms": common_terms, "claim_refs": rec["claim_refs"], "source_refs": rec["source_refs"], "coverage_conclusion": "not_assessed"})
        reviews.append({"invention_id": inv["id"], "title": inv["title"], "business_score": None if missing else fmt(weighted), "score_status": "incomplete" if missing else "complete", "missing_criteria": missing, "criterion_calculations": contributions, "meets_approved_business_threshold": threshold_result, "bucket_mappings": [buckets[b] for b in inv["bucket_ids"]], "supplied_gap_alignments": [gaps[g] for g in inv["gap_ids"]], "candidate_portfolio_records": candidates, "portfolio_conclusion": "candidate_review_required" if candidates else "no_candidates_in_supplied_records_gap_not_established", "legal_filing_decision": "reserved_for_counsel"})
    budget = data["budget"]
    baseline = money(budget["spent"], "spent") + money(budget["committed"], "committed")
    limit = money(budget["limit"], "limit")
    scenarios = []
    for scenario in data["scenarios"]:
        lines, outside = [], []
        quarter_totals = {}
        for lid in scenario["plan_line_ids"]:
            line = plan[lid]
            amount = money(costs[line["cost_id"]]["unit_cost"], "unit_cost") * line["quantity"]
            row = {**line, "unit_cost": fmt(money(costs[line["cost_id"]]["unit_cost"], "unit_cost")), "amount": fmt(amount), "cost_source_refs": costs[line["cost_id"]]["source_refs"]}
            if budget["start"] <= line["expected_date"] <= budget["end"]:
                lines.append(row)
                dt = day(line["expected_date"], "expected_date")
                quarter = f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
                quarter_totals[quarter] = quarter_totals.get(quarter, Decimal(0)) + amount
            else:
                outside.append(row)
        new_cost = sum((Decimal(line["amount"]) for line in lines), Decimal(0))
        reserve = (new_cost * number(budget["contingency_percent"], "contingency") / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        forecast = baseline + new_cost + reserve
        scenarios.append({"id": scenario["id"], "description": scenario["description"], "included_lines": lines, "outside_period_lines": outside, "new_cost_by_quarter_excluding_contingency": {q: fmt(v) for q, v in sorted(quarter_totals.items())}, "new_cost": fmt(new_cost), "contingency": fmt(reserve), "baseline_spent_plus_committed": fmt(baseline), "forecast_total": fmt(forecast), "headroom": fmt(limit - forecast), "over_budget": forecast > limit, "timing_or_filing_authorization": "none"})
    return {"schema_version": "1.0", "policy_id": policy["id"], "policy_state": policy["state"], "business_threshold": policy["business_threshold"], "invention_reviews": reviews, "portfolio_summary": {"supplied_record_count": len(portfolio), "known_family_count": len({r["family_id"] for r in portfolio.values() if r["family_id"] is not None}), "records_with_unknown_family": sum(r["family_id"] is None for r in portfolio.values()), "record_counts_by_status": {s: sum(r["status"] == s for r in portfolio.values()) for s in ("pending", "issued", "expired", "abandoned", "unknown")}, "scope": "supplied_records_only_status_not_independently_verified"}, "currency": budget["currency"], "budget_period": {"start": budget["start"], "end": budget["end"]}, "budget_source_refs": budget["source_refs"], "budget_limit": budget["limit"], "contingency_percent": budget["contingency_percent"], "scenarios": scenarios, "limitations": ["Scores assess supplied business ratings, not patentability or legal filing decisions.", "Exact tag matching only; no semantic search or claim analysis.", "Source locators are retained, not independently verified by this calculator.", "All plan costs must be incremental to spent and committed; duplicates with baseline cannot be detected.", "Single currency with two-decimal monetary precision; no exchange-rate or legal fee lookup.", "Scenario dates are cost forecasts, not computed legal deadlines."]}


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        # Preserve JSON fractional values as decimal strings, never binary floats.
        data = json.loads(args.input.read_text(), parse_float=str, object_pairs_hook=no_duplicates)
        result = evaluate(data)
    except (InputError, json.JSONDecodeError, OSError, InvalidOperation, TypeError) as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

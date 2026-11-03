#!/usr/bin/env python3
"""Offline organization/portfolio inventory and strategy-gap triage. Python 3.10+."""
import argparse
import csv
from datetime import date
import json
from pathlib import Path
import re
import sys


class InputError(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise InputError(message)


def text(value, label):
    need(isinstance(value, str) and bool(value.strip()), label + ": expected nonempty text")
    return value


def obj(value, keys, label):
    need(isinstance(value, dict), label + ": expected object")
    need(set(value) == set(keys), label + ": incorrect fields; expected " + ", ".join(keys))


def day(value, label):
    text(value, label)
    need(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None, label + ": use YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise InputError(label + ": invalid date") from None


def items(value, label):
    need(isinstance(value, list), label + ": expected list")
    return value


def strings(value, label, nonempty=False):
    items(value, label)
    for v in value:
        text(v, label)
    need(len(set(value)) == len(value), label + ": duplicate value")
    need(not nonempty or bool(value), label + ": at least one source/value is required")
    return value


def refs(value):
    strings(value, "source_refs", True)


def integer(value, label, low=0):
    need(type(value) is int and low <= value <= 1000000, label + ": expected bounded integer")


def index(value, label):
    result = {}
    for row in items(value, label):
        need(isinstance(row, dict) and "id" in row, label + ": records require id")
        ident = text(row["id"], label + ".id")
        need(ident not in result, label + ": duplicate id " + ident)
        result[ident] = row
    return result


def foreign(value, known, label):
    strings(value, label)
    need(set(value) <= set(known), label + ": unknown reference")


def validate(data):
    obj(data, ["schema_version", "as_of", "review_window_days", "inventory_scope", "teams", "people", "products", "buckets", "targets", "records", "disclosures", "assessments"], "input")
    need(data["schema_version"] == "1.0", "Unsupported schema_version")
    as_of = day(data["as_of"], "as_of")
    integer(data["review_window_days"], "review_window_days", 1)
    text(data["inventory_scope"], "inventory_scope")
    teams, people, products, buckets, targets, records, disclosures, assessments = [index(data[k], k) for k in ("teams", "people", "products", "buckets", "targets", "records", "disclosures", "assessments")]
    for row in teams.values():
        obj(row, ["id", "name", "parent_id", "source_refs"], "team")
        text(row["name"], "team.name"); refs(row["source_refs"])
        need(row["parent_id"] is None or isinstance(row["parent_id"], str) and row["parent_id"] in teams, "team: unknown parent")
    for ident in teams:
        seen = set(); cursor = ident
        while cursor is not None:
            need(cursor not in seen, "team: organization cycle")
            seen.add(cursor); cursor = teams[cursor]["parent_id"]
    for row in people.values():
        obj(row, ["id", "name", "team_ids", "source_refs"], "person")
        text(row["name"], "person.name"); foreign(row["team_ids"], teams, "person.team_ids"); refs(row["source_refs"])
    for row in products.values():
        obj(row, ["id", "name", "source_refs"], "product")
        text(row["name"], "product.name"); refs(row["source_refs"])
    for row in buckets.values():
        obj(row, ["id", "name", "description", "team_ids", "product_ids", "person_ids", "source_refs"], "bucket")
        for key in ("name", "description"):
            text(row[key], "bucket." + key)
        foreign(row["team_ids"], teams, "bucket.team_ids")
        foreign(row["product_ids"], products, "bucket.product_ids")
        foreign(row["person_ids"], people, "bucket.person_ids"); refs(row["source_refs"])
    for row in targets.values():
        obj(row, ["id", "bucket_id", "feature", "technical_tags", "jurisdiction", "horizon", "priority", "objective", "desired_family_count", "source_refs"], "target")
        need(isinstance(row["bucket_id"], str) and row["bucket_id"] in buckets, "target: unknown bucket")
        for key in ("feature", "jurisdiction", "horizon"):
            text(row[key], "target." + key)
        strings(row["technical_tags"], "target.technical_tags")
        need(row["priority"] in ("high", "medium", "low"), "target: invalid priority")
        need(row["objective"] in ("product", "offensive", "defensive"), "target: invalid objective")
        integer(row["desired_family_count"], "desired_family_count"); refs(row["source_refs"])
    public_ids = set()
    for row in records.values():
        obj(row, ["id", "title", "family_id", "application_id", "publication_id", "patent_id", "jurisdiction", "status", "status_as_of", "filing_date", "priority_date", "technical_tags", "bucket_links", "claim_refs", "source_refs"], "record")
        for key in ("title", "jurisdiction"):
            text(row[key], "record." + key)
        for key in ("family_id", "application_id", "publication_id", "patent_id"):
            if row[key] is not None:
                text(row[key], key)
        for key in ("application_id", "publication_id", "patent_id"):
            if row[key] is not None:
                marker = (row["jurisdiction"].strip().casefold(), key, row[key].strip().casefold())
                need(marker not in public_ids, "Duplicate public identifier: " + str(marker))
                public_ids.add(marker)
        need(row["status"] in ("pending", "issued", "expired", "abandoned", "unknown"), "record: invalid status")
        for key in ("status_as_of", "filing_date", "priority_date"):
            if row[key] is not None:
                need(day(row[key], key) <= as_of, "record dates cannot follow as_of")
        if row["filing_date"] and row["priority_date"]:
            need(row["priority_date"] <= row["filing_date"], "priority_date cannot follow filing_date")
        strings(row["technical_tags"], "record.technical_tags"); strings(row["claim_refs"], "claim_refs"); refs(row["source_refs"])
        seen = set()
        for link in items(row["bucket_links"], "bucket_links"):
            obj(link, ["bucket_id", "state", "rationale", "source_refs"], "bucket link")
            need(isinstance(link["bucket_id"], str) and link["bucket_id"] in buckets, "link: unknown bucket")
            need(link["bucket_id"] not in seen, "duplicate bucket link")
            seen.add(link["bucket_id"])
            need(link["state"] in ("confirmed", "proposed"), "link.state: confirmed or proposed")
            text(link["rationale"], "link.rationale"); refs(link["source_refs"])
    for row in disclosures.values():
        obj(row, ["id", "title", "bucket_ids", "target_ids", "stage", "source_refs"], "disclosure")
        text(row["title"], "disclosure.title")
        foreign(row["bucket_ids"], buckets, "disclosure.bucket_ids")
        foreign(row["target_ids"], targets, "disclosure.target_ids")
        for tid in row["target_ids"]:
            need(targets[tid]["bucket_id"] in row["bucket_ids"], "disclosure target belongs to an unassigned bucket")
        need(row["stage"] in ("intake", "review", "approved_to_file", "filed", "declined"), "disclosure: invalid stage")
        refs(row["source_refs"])
    assessed_targets = set()
    for row in assessments.values():
        obj(row, ["id", "target_id", "result", "reviewer", "reviewed_on", "record_ids", "rationale", "source_refs"], "assessment")
        need(isinstance(row["target_id"], str) and row["target_id"] in targets, "assessment: unknown target")
        need(row["target_id"] not in assessed_targets, "Only one current assessment per target; archive superseded reviews separately")
        assessed_targets.add(row["target_id"])
        need(row["result"] in ("supports", "partial", "gap", "unknown"), "assessment: invalid result")
        text(row["reviewer"], "assessment.reviewer"); text(row["rationale"], "assessment.rationale")
        need(day(row["reviewed_on"], "reviewed_on") <= as_of, "assessment cannot follow as_of")
        foreign(row["record_ids"], records, "assessment.record_ids"); refs(row["source_refs"])
        target = targets[row["target_id"]]
        for rid in row["record_ids"]:
            need(records[rid]["jurisdiction"] == target["jurisdiction"], "assessment record jurisdiction must match target")
        if row["result"] in ("supports", "partial"):
            need(bool(row["record_ids"]), "support/partial assessment requires record references")
            for rid in row["record_ids"]:
                rec = records[rid]
                need(rec["status"] == "issued" and bool(rec["claim_refs"]), "support/partial assessment requires issued records with claim locators")
    return as_of, teams, people, products, buckets, targets, records, disclosures, assessments


def run(data):
    as_of, teams, people, products, buckets, targets, records, disclosures, assessments = validate(data)
    window = data["review_window_days"]
    def freshness(rec):
        if rec["status_as_of"] is None:
            return "undated"
        return "stale" if (as_of - day(rec["status_as_of"], "status_as_of")).days > window else "within_review_window"
    def count(rows):
        return {"records": len(rows), "known_families": len({r["family_id"] for r in rows if r["family_id"] is not None}), "records_with_unknown_family": sum(r["family_id"] is None for r in rows), "by_status": {s: sum(r["status"] == s for r in rows) for s in ("pending", "issued", "expired", "abandoned", "unknown")}, "by_jurisdiction": {j: {"records": sum(r["jurisdiction"] == j for r in rows), "published_application_records": sum(r["jurisdiction"] == j and r["publication_id"] is not None for r in rows), "by_status": {s: sum(r["jurisdiction"] == j and r["status"] == s for r in rows) for s in ("pending", "issued", "expired", "abandoned", "unknown")}} for j in sorted({r["jurisdiction"] for r in rows})}}
    target_reviews = []
    assessment_by_target = {a["target_id"]: a for a in assessments.values()}
    for target in targets.values():
        candidates = []
        proposed = []
        tags = {t.strip().casefold() for t in target["technical_tags"]}
        for rec in records.values():
            links = [l for l in rec["bucket_links"] if l["bucket_id"] == target["bucket_id"]]
            if rec["jurisdiction"] != target["jurisdiction"] or not links:
                continue
            item = {"record_id": rec["id"], "family_id": rec["family_id"], "status": rec["status"], "status_freshness": freshness(rec), "shared_tags": sorted(tags & {t.strip().casefold() for t in rec["technical_tags"]}), "mapping": links[0], "claim_refs": rec["claim_refs"], "source_refs": rec["source_refs"]}
            (candidates if links[0]["state"] == "confirmed" else proposed).append(item)
        active = [r for r in candidates if r["status"] in ("pending", "issued")]
        families = {r["family_id"] for r in active if r["family_id"] is not None}
        # This signal is inventory triage, never a claim-coverage finding.
        if not candidates:
            signal = "no_confirmed_mapped_records"
        elif any(r["status"] == "issued" for r in candidates):
            signal = "issued_candidates_require_claim_review"
        elif any(r["status"] == "pending" for r in candidates):
            signal = "pending_candidates_only_no_issued_records"
        elif all(r["status"] in ("expired", "abandoned") for r in candidates):
            signal = "inactive_candidates_only"
        else:
            signal = "status_unknown_review_required"
        assessment = assessment_by_target.get(target["id"])
        blockers = []
        if assessment:
            if (as_of - day(assessment["reviewed_on"], "reviewed_on")).days > window:
                blockers.append("assessment_outside_review_window")
            for rid in assessment["record_ids"]:
                if freshness(records[rid]) != "within_review_window":
                    blockers.append("record_status_needs_refresh:" + rid)
        effective = assessment["result"] if assessment and not blockers else "not_currently_established"
        target_reviews.append({"target": target, "inventory_signal": signal, "candidate_records": candidates, "proposed_mapping_candidates": proposed, "active_known_family_count": len(families), "active_records_with_unknown_family": sum(r["family_id"] is None for r in active), "planning_family_shortfall": max(0, target["desired_family_count"] - len(families)), "planning_count_basis": "confirmed_bucket_mapping_same_jurisdiction_pending_or_issued_known_family_labels_not_feature_coverage", "pipeline": [d for d in disclosures.values() if target["id"] in d["target_ids"]], "open_disclosure_count": sum(target["id"] in d["target_ids"] and d["stage"] in ("intake", "review", "approved_to_file") for d in disclosures.values()), "reported_counsel_assessment": assessment, "assessment_refresh_reasons": blockers, "current_recorded_assessment": effective, "legal_gap_inferred_by_software": False})
    bucket_reviews = []
    for bucket in buckets.values():
        confirmed = [r for r in records.values() if any(l["bucket_id"] == bucket["id"] and l["state"] == "confirmed" for l in r["bucket_links"])]
        proposed = [r["id"] for r in records.values() if any(l["bucket_id"] == bucket["id"] and l["state"] == "proposed" for l in r["bucket_links"])]
        bucket_reviews.append({"bucket": bucket, "teams": [teams[i] for i in bucket["team_ids"]], "products": [products[i] for i in bucket["product_ids"]], "people": [people[i] for i in bucket["person_ids"]], "ownership_needs_assignment": not bool(bucket["team_ids"]), "inventory": count(confirmed), "confirmed_record_ids": [r["id"] for r in confirmed], "proposed_record_ids": proposed, "disclosures": [d for d in disclosures.values() if bucket["id"] in d["bucket_ids"]], "open_disclosure_count": sum(bucket["id"] in d["bucket_ids"] and d["stage"] in ("intake", "review", "approved_to_file") for d in disclosures.values()), "target_ids": [t["id"] for t in targets.values() if t["bucket_id"] == bucket["id"]]})
    warnings = [{"type": "status_refresh", "record_id": r["id"], "freshness": freshness(r)} for r in records.values() if freshness(r) != "within_review_window"]
    warnings += [{"type": "missing_public_identifiers", "record_id": r["id"]} for r in records.values() if all(r[k] is None for k in ("application_id", "publication_id", "patent_id"))]
    warnings += [{"type": "unknown_family", "record_id": r["id"]} for r in records.values() if r["family_id"] is None]
    unmapped = [r["id"] for r in records.values() if not any(l["state"] == "confirmed" for l in r["bucket_links"])]
    # Compatible context only. Copy into a filing-review input after human review; does not create ratings or costs.
    context = {"strategy": {"buckets": [{"id": b["id"], "name": b["name"], "team": ", ".join(teams[i]["name"] for i in b["team_ids"]) or "Unassigned — needs review", "source_refs": b["source_refs"]} for b in buckets.values()], "gaps": [{"id": t["target"]["id"], "bucket_id": t["target"]["bucket_id"], "description": t["target"]["feature"] + " — " + t["reported_counsel_assessment"]["rationale"], "source_refs": t["reported_counsel_assessment"]["source_refs"]} for t in target_reviews if t["current_recorded_assessment"] == "gap"]}, "portfolio": [{"id": r["id"], "title": r["title"], "family_id": r["family_id"], "jurisdiction": r["jurisdiction"], "status": r["status"], "status_as_of": r["status_as_of"], "bucket_ids": [l["bucket_id"] for l in r["bucket_links"] if l["state"] == "confirmed"], "technical_terms": r["technical_tags"], "claim_refs": r["claim_refs"], "source_refs": r["source_refs"]} for r in records.values()]}
    return {"schema_version": "1.0", "as_of": data["as_of"], "inventory_scope": data["inventory_scope"], "review_window_days": window, "organization": {"teams": list(teams.values()), "people": list(people.values()), "products": list(products.values())}, "portfolio_inventory": count(list(records.values())), "portfolio_records": list(records.values()), "bucket_reviews": bucket_reviews, "target_reviews": target_reviews, "unmapped_or_proposed_only_record_ids": unmapped, "data_quality_warnings": warnings, "filing_review_context": context, "limitations": ["Counts refer only to supplied records and family labels; bucket totals are not additive.", "Bucket mappings and tags are classifications, not claim coverage, novelty, or freedom to operate.", "Planning shortfalls compare known mapped family labels to targets, not required new filings.", "Recorded counsel conclusions and reviewer identities are supplied data, not authenticated or independently verified.", "A review window is a company data-freshness policy, not a legal validity rule.", "Pipeline disclosures are not issued or pending application coverage; no software filing decision is made."]}


CSV_FIELDS = ["id", "title", "family_id", "application_id", "publication_id", "patent_id", "jurisdiction", "status", "status_as_of", "filing_date", "priority_date", "technical_tags", "confirmed_bucket_ids", "proposed_bucket_ids", "mapping_rationale", "claim_refs", "source_refs"]


def load_csv(path):
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        need(reader.fieldnames is not None and len(reader.fieldnames) == len(set(reader.fieldnames)) and set(reader.fieldnames) == set(CSV_FIELDS), "CSV header must match the documented columns exactly")
        result = []
        for row in reader:
            need(None not in row and all(v is not None for v in row.values()), "CSV row has incorrect column count")
            split = lambda key: [v.strip() for v in row[key].split("|") if v.strip()]
            sources = split("source_refs")
            links = [{"bucket_id": bid, "state": state, "rationale": row["mapping_rationale"].strip(), "source_refs": sources} for col, state in (("confirmed_bucket_ids", "confirmed"), ("proposed_bucket_ids", "proposed")) for bid in split(col)]
            result.append({**{k: row[k].strip() for k in ("id", "title", "jurisdiction", "status")}, **{k: row[k].strip() or None for k in ("family_id", "application_id", "publication_id", "patent_id", "status_as_of", "filing_date", "priority_date")}, "technical_tags": split("technical_tags"), "bucket_links": links, "claim_refs": split("claim_refs"), "source_refs": sources})
        return result


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "Duplicate JSON key: " + key)
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--records-csv", type=Path, help="Replace records list; input records must be empty")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(), object_pairs_hook=no_duplicates)
        if args.records_csv:
            need(isinstance(data, dict) and data.get("records") == [], "CSV import requires input records: [] to avoid accidental replacement")
            data["records"] = load_csv(args.records_csv)
        output = run(data)
    except (InputError, OSError, json.JSONDecodeError, csv.Error, TypeError, UnicodeError) as exc:
        print("Input error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

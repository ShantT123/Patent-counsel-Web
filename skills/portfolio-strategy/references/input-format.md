# Strategy input, record import, and output

Python 3.10+; standard library only. JSON version `"1.0"`. All fields listed below are required. Empty lists and documented null values represent unknown or unavailable information. Undocumented fields, unknown references, duplicate IDs, cycles, and malformed dates are rejected.

## Top level

`schema_version`, `as_of` (YYYY-MM-DD), `review_window_days` (integer 1..1,000,000), `inventory_scope` (nonempty source-scope description), plus the lists below. The explicit as-of date makes reports reproducible. No current date, status, or legal deadline is fetched.

| List | Fields per record |
| --- | --- |
| teams | `id`, `name`, `parent_id` (team ID or null), `source_refs` |
| people | `id`, `name`, `team_ids`, `source_refs` |
| products | `id`, `name`, `source_refs` |
| buckets | `id`, `name`, `description`, `team_ids`, `product_ids`, `person_ids`, `source_refs` |
| targets | `id`, `bucket_id`, `feature`, `technical_tags`, `jurisdiction`, `horizon`, `priority`, `objective`, `desired_family_count`, `source_refs` |
| records | `id`, `title`, `family_id`, `application_id`, `publication_id`, `patent_id`, `jurisdiction`, `status`, `status_as_of`, `filing_date`, `priority_date`, `technical_tags`, `bucket_links`, `claim_refs`, `source_refs` |
| disclosures | `id`, `title`, `bucket_ids`, `target_ids`, `stage`, `source_refs` |
| assessments | `id`, `target_id`, `result`, `reviewer`, `reviewed_on`, `record_ids`, `rationale`, `source_refs` |

IDs are stable strings unique within each list. source_refs are nonempty lists of document/section or similar locators; they are retained but not independently verified. Names/titles and required descriptions must be nonempty. All referenced IDs must exist. ID and jurisdiction matching is exact/case-sensitive; normalize input conventions deliberately.

A bucket may have no owner or mapped people; this surfaces an ownership issue rather than fabricating an assignment. A disclosure's target must belong to one of its assigned buckets. Other lists may be empty, allowing a partial inventory.

## Targets and records

Priority: `high`, `medium`, `low`. Objective: `product`, `offensive`, `defensive`. desired_family_count: integer 0..1,000,000, a business planning target only.

Record family/public identifiers may be null. Public identifiers are preserved as supplied, not format-validated or looked up. Each record represents one application/jurisdiction; retain its publication/grant IDs on that same row. Duplicate nonnull public identifiers of the same field/jurisdiction are rejected after trimming/case folding. Different formatting of the same identifier may evade detection; human reconciliation is still required. Family IDs are never inferred from titles.

Status: `pending`, `issued`, `expired`, `abandoned`, `unknown`. status_as_of, filing_date, and priority_date may be null; nonnull dates cannot follow as_of. Priority cannot follow filing when both dates exist. These are supplied administrative facts, not independently verified legal status or priority entitlement.

Each bucket_links entry has `bucket_id`, `state` (`confirmed` or `proposed`), `rationale`, `source_refs`. A confirmed classification is a user/reviewer mapping, not a claim-coverage finding. A record cannot repeat a bucket link. claim_refs are source locator strings and may be empty.

## Disclosures and assessments

Disclosure stage: `intake`, `review`, `approved_to_file`, `filed`, `declined`. Only the first three count as open disclosures. Stages record supplied business status and do not themselves authorize action or create application records.

Assessment result: `supports`, `partial`, `gap`, `unknown`. One current assessment per target; keep superseded history outside this input. Reviewer is supplied metadata, not an authenticated legal credential. reviewed_on cannot follow as_of. Any referenced records must match the target jurisdiction; supports/partial need at least one issued record with a claim locator. This is a structural prerequisite, not legal analysis.

If the assessment age exceeds review_window_days, or any referenced record status is undated or older than the window, the effective result becomes `not_currently_established` with explicit refresh reasons. Equality at the window boundary is within-window. Original assessment data is preserved. An unknown current assessment stays unknown.

## CSV import

Use an input with `records: []`, then:

```sh
python3 scripts/strategy.py INPUT.json --records-csv RECORDS.csv
```

The CSV replaces only the empty records list; attempts to replace nonempty data are rejected. UTF-8 with optional BOM is accepted. Header names must match this exact set (order may differ):

```text
id,title,family_id,application_id,publication_id,patent_id,jurisdiction,status,status_as_of,filing_date,priority_date,technical_tags,confirmed_bucket_ids,proposed_bucket_ids,mapping_rationale,claim_refs,source_refs
```

Use `|` to separate tags, bucket IDs, claim locators, and source locators. Empty optional identifier/date fields become null. CSV mapping_rationale and source_refs apply to all bucket links on that row; use JSON for more granular mapping sources. Mapping rationale may be empty only when both bucket-ID cells are empty. Values containing literal `|` are not supported in multivalue cells; use JSON instead. CSV quoting follows standard rules. Malformed rows/duplicate headers are rejected. The example CSV is equivalent to the example JSON.

## Output interpretation

- portfolio_inventory: supplied record counts, unique known family labels, unknown-family rows, and jurisdiction/status/publication counts. Publication counts mean nonnull publication_id, not an independently verified public application.
- portfolio_records: normalized supplied records for audit. Bucket summaries contain confirmed mappings only and list proposed mappings separately. Multi-bucket counts are not additive.
- target_reviews: same-jurisdiction records with bucket links. Confirmed and proposed mappings are separate. All same-bucket candidates are shown even without shared tags; shared_tags is explanatory exact trimmed/case-folded intersection, not relevance scoring.
- active_known_family_count: unique known family labels among confirmed pending/issued candidate records. planning_family_shortfall = max(0, desired_family_count minus this count). Unknown-family rows are separately visible. This is not a technical coverage gap or filing quota.
- current_recorded_assessment: supplied assessment if within-window with sufficiently dated referenced records; otherwise not_currently_established. No software legal gap is inferred.
- filing_review_context: compatible `strategy` and `portfolio` objects for the existing filing-review input; only current recorded `gap` assessments export as gaps, and only confirmed bucket links export as record bucket_ids. The broader source scope remains in this report and must accompany a handoff. It is not a complete filing-review input.

JSON goes to stdout; validation errors to stderr with exit code 2. No files are overwritten or uploaded. Preserve input, output, and version together. The CLI performs no external search, legal verification, or document parsing beyond supplied JSON/CSV.

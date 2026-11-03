# Calculator input format and formulas

Python 3.10+; standard library only. All fields below are required unless explicitly optional. Unknown keys are rejected to surface typos. JSON duplicate keys are rejected by the CLI. IDs must be unique within their lists; list references must resolve. Source locators are nonempty strings, not fetched or checked for truth.

Use the repository's `examples/filing-review/input.json` as a complete editable example. An installed skill can use this reference to construct inputs without that example.

## Top-level objects

- `schema_version`: `"1.0"`.
- `policy`: `id`, `state` (`draft` or `approved`), `business_threshold` (0–100), `criteria`. Approved policies additionally require `approved_by` and `approved_on` (YYYY-MM-DD). These record user-supplied approval, not authenticated authority.
- `strategy`: `buckets` and `gaps` lists; either may be empty.
- `inventions`, `portfolio`, `plan`, `scenarios`: lists. Portfolio/plan may be empty; at least one explicit scenario and criterion are required.
- `cost_catalog`: `currency` (uppercase three-letter code), `items` list.
- `budget`: `currency`, `start`, `end`, `limit`, `spent`, `committed`, `contingency_percent`, `source_refs`.

Money must be a nonnegative decimal string or integer with at most two fractional digits. Currency must match between catalog and budget. This version supports two-decimal monetary precision only and does not validate the code against an exchange-rate or currency database. No FX conversion is performed. Monetary inputs are limited to 1 trillion per field. All numeric inputs must be finite. JSON fractional numbers are read as exact decimal strings; decimal strings are recommended for clarity.

## List records

| List | Record fields |
| --- | --- |
| criteria | `id`, `description` (include scale meaning), `weight` (>0), `min`, `max` (>min). Higher is always more favorable. |
| buckets | `id`, `name`, `team`, `source_refs` |
| gaps | `id`, `bucket_id`, `description`, `source_refs` |
| inventions | `id`, `title`, `bucket_ids`, `technical_terms`, `gap_ids`, `source_refs`, `ratings` |
| portfolio | `id`, `title`, `family_id` (string or null), `jurisdiction`, `status`, `status_as_of` (date or null), `bucket_ids`, `technical_terms`, `claim_refs`, `source_refs` |
| cost items | `id`, `description` (state inclusions/exclusions), `unit_cost`, `source_refs` |
| plan | `id`, `invention_id`, `cost_id`, `quantity` (positive integer <=1,000,000), `expected_date`, `source_refs` |
| scenarios | `id`, `description`, `plan_line_ids` (unique selected plan IDs; may be empty) |

Each `ratings` object maps criterion IDs to `{ "value": 8, "rationale": "Reviewer judgment...", "source_refs": ["review note §2"] }`. Omitted criterion or `value: null` means unknown. Null entries still need a rationale and a source_refs list, which may be empty. Known ratings require nonempty source_refs and must lie within the criterion's configured scale. Unknown criterion IDs are rejected.

Portfolio status is one of `pending`, `issued`, `expired`, `abandoned`, `unknown`. A gap assigned to an invention must belong to one of its assigned buckets. `claim_refs` may be empty; no claims are evaluated by the script.

## Score calculation

For each criterion: normalized = 100 × (rating − min) / (max − min).

Weighted score = sum(normalized × weight) / sum(all configured weights).

Weights need not add to 100. A missing criterion makes the overall score null; known criterion contributions remain visible as an audit trail, not a partial overall score. Output is displayed to two decimals. Threshold comparison uses the unrounded score; a displayed 70.00 may still be below a 70 threshold if the underlying score is slightly lower. Complete draft-policy scores are illustrative and receive a null approved-threshold result.

## Portfolio calculation

Candidates share at least one bucket ID **or** one exact technical-term tag after trimming and case folding. This is an OR match, not a semantic similarity model. Results show why each record matched and retain sources, family, jurisdiction, status/date, and claim references. Even a strong match has `coverage_conclusion: not_assessed`.

## Budget calculation

Include only selected plan lines whose expected dates fall inside the inclusive start/end period. List selected out-of-period lines separately; do not silently discard them. A period spanning multiple years is supported.

- Line amount = quantity × catalog unit cost.
- New cost = sum(in-period selected line amounts).
- Reserve = new cost × contingency_percent / 100, rounded once to cents using ROUND_HALF_UP.
- Baseline = spent + remaining committed.
- Forecast total = baseline + new cost + reserve.
- Headroom = limit − forecast total; negative means over budget.

The reserve applies only to new cost, not baseline. The quarterly breakout includes new cost only, before reserve; baseline and reserve are not allocated to quarters. A quarter may be partial if the budget period starts/ends midquarter. `over_budget` is true only when forecast strictly exceeds the limit.

Expected dates are cost recognition assumptions, not computed legal deadlines. Different scenarios can select the same line; a line cannot appear twice within one scenario. One scenario never mutates another or the source data. All plan lines must be incremental to baseline, which cannot be verified from amount totals alone.

## Running

From the skill directory:

```sh
python3 scripts/review.py /path/to/input.json
```

Successful output is JSON on stdout. Validation errors go to stderr with exit status 2. The script never uploads data, creates output directories, or overwrites a report; redirect/capture stdout when saving is desired. Retain the input and version alongside saved results for reproducibility.

# PizzaHut-Intelligence takeover audit

Audit date: 17 November 2026

## Repository and implementation state

- Git history contains `b02954a` (SQLite schema, repository, validator, and first tests) and `6a022d0` (Streamlit dashboard, reports, data seeder, and Papa John's collector).
- The working tree already contained uncommitted work at takeover: schema additions for benchmarks/quarantine, `src/db/migrate.py`, matching engine/service files, scraper hub/Papa John's scraper, and SQLite WAL sidecars. Those files were inspected and retained.
- The existing app is a Streamlit dashboard backed by SQLite. It has catalog, collection, QA, evidence, comparison, history, and report views.
- Antigravity stopped before a working Pizza Hut extraction path: `ScraperHub` only probes the Pizza Hut Talabat landing page and records zero extracted items. The only live HTML scraper targets Papa John's. The benchmark service instead contains hard-coded prices for four competitors, and the evaluator originally matched only name and size.
- The checked-in project brief still described implementation as not started; it did not document the later dashboard or the unfinished state.

## Test baseline

- `.venv/bin/python -m pytest -q` could not start because `pytest` is not installed in the project venv or system Python.
- The repository uses `unittest`; `.venv/bin/python -m unittest discover -v` ran the existing 17 tests successfully before edits.
- After changes, the suite contains 26 tests. Run it with `.venv/bin/python -m unittest discover -v`.

## Read-only production database audit

The takeover-state database was inspected through SQLite read-only mode before the Pizza Hut pilot run. No pre-existing observation, benchmark, evidence, or seed row was changed by that audit.

| Records | Stored state | Audit result |
|---|---|---|
| 125 `live_extraction` observations | All attributed to Papa John's UAE; all labelled `verified`; all unquarantined | 83 have a product-type / variant assignment that needs review. |
| 684 `quarantined_seed` observations | All labelled `needs_review`; all `is_quarantined=1` | Left quarantined. |
| 40 benchmark rows | 10 Pizza Hut, 10 Domino's, 14 Papa John's, 6 Freedom Pizza | All came from the hard-coded seeder with generic storefront URLs and generic “Manually audited ground-truth benchmark price” notes. None has a benchmark-specific evidence link. The evaluator must not trust them yet. |

Of the 83 live rows flagged, 60 are recognizable non-pizza items stored in the `pizza` category with pizza-like variants (including burgers, sandwiches, Papadias, sides, pasta, salad, desserts, drinks, sauces, and packets). The other 23 are combo / meal records with pizza size/crust fields; they are not standalone pizza prices and need item-level review before matching.

All 125 live rows point to one evidence record and one Papa John's HTML snapshot (`data/evidence/papajohns_menu_1794915551.html`, SHA-256 `f8ee863a82ae26906a81e2bed913004e50a703523d35af2ab451a6da413bb33b`). This proves a page was captured, but it does not fix the observed type/variant mismatches or independently validate the scraper's item-to-price pairing.

Although all 125 rows carry a verified label, the accuracy evaluator now treats those original records as uncertain until a human QA revision is appended. The 42 rows without an obvious type/variant flag are still not automatically trusted.

The complete takeover-state 125-row audit, including each observation ID, category, size, crust, price, source, timestamp, evidence ID, and review flag, is in [`data/research/live_extraction_audit.csv`](data/research/live_extraction_audit.csv).

## Source research for the first Pizza Hut workflow

- Pizza Hut's official UAE menu has a public pizza catalog and product pages. The catalog separates pizzas, starters, meals, drinks, and desserts.
- The official product pages expose names, small/medium/large variants, slice counts, AED prices, and (on some pages) alternative crust names. For example, the public Margarita page shows Small 4 slices AED 18, Medium 6 slices AED 28, Large 8 slices AED 39; Hawaiian shows AED 20/31/44; the Cheesy Jalapeno Stuffed Crust Pizza page shows Medium AED 36 and Large AED 51.
- Pizza Hut's official online ordering site is branch-aware, and the Talabat landing page asks customers to select an area before showing a restaurant menu. Regional catalog prices therefore cannot be treated as branch/channel checkout prices without a branch-level capture.
- These observed public menu facts are listed as **candidates only** in [`data/research/pizzahut_menu_benchmark_candidates.json`](data/research/pizzahut_menu_benchmark_candidates.json). They have not been inserted into the benchmark table and must be recaptured for the selected branch/channel before accuracy scoring.

## Changes made after the audit

- Added a Pizza Hut public-menu collector that stores source-page HTML snapshots with SHA-256 hashes and timestamps, extracts only explicit pizza size/price pairs, and sends every extracted observation to `needs_review`.
- Added a read-only live-observation quality audit and surfaced it in the existing collection view.
- Changed manual collection so non-pizza products use size `other` and crust `Not applicable`; unknown entries default to `needs_review`.
- Removed hard-coded benchmark fixtures from the benchmark service. The old 40 rows remain in the database but are classified as untrusted/uncertain unless a new append-only case has a matching captured evidence artifact.
- Tightened scoring to exact competitor, pizza category, canonical name, size, emirate, and channel. A percentage is emitted only for correct/incorrect evaluated cases; missing and uncertain are reported separately.
- Revisions and corrections append new observation rows. The review UI no longer offers observation deletion. Quarantined seed rows cannot be promoted through the correction path.
- Replaced the synthetic 684-row seeder with a reference-data-only compatibility shim and removed the dashboard's database reset action. Existing production rows and the quarantined seed data were not touched.

## Live Pizza Hut pilot run

The collector successfully fetched the public Pizza Hut UAE pizza catalog and product pages on 17 November 2026. The successful run UUID is `b5d11ea0-8b47-43dd-aba8-57176a2e6d95`; it extracted 31 size/price observations across Pizza Hut pizza products, stored timestamped SHA-256 HTML captures, and left all 31 at `needs_review` (zero marked verified). The captures confirm explicit slice counts, sizes, prices, and available crust labels where the public page includes them. The candidate JSON links its Margarita, Hawaiian, and Cheesy Jalapeno cases to their captured evidence records.

After that run, the database contains 840 observations total: the original 125 Papa John's live rows (still marked verified and now surfaced for QA), 31 new Pizza Hut live rows in `needs_review`, and the original 684 seed rows still quarantined. All 40 legacy benchmarks are retained and treated as uncertain; there are currently zero evidence-backed benchmark cases, so no accuracy percentage is available. The run history contains three completed runs and three failed attempts, all recorded with their actual outcomes.

Two earlier run attempts failed before writing observations, and one parser-debug run captured pages but extracted none. Those runs remain in `research_runs` with their actual failure statuses; they are part of the audit trail.

Branch selection, ordering-channel confirmation, crust-specific prices, and checkout fees still require QA against the official ordering site or selected branch. The regional menu observations are not promoted to benchmark truth. No 41% or 97% accuracy claim is made.

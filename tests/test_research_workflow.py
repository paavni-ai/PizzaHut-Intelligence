import hashlib
import tempfile
import unittest
from pathlib import Path

from src.db.connection import get_connection
from src.db.init_db import initialize_database
from src.db.repository import PizzaIntelligenceRepository
from src.db.validator import DatabaseValidator
from src.matching.accuracy_engine import AccuracyEngine
from src.matching.benchmark_service import add_verified_benchmark, get_all_benchmarks, seed_ground_truth_benchmarks
from src.scrapers.pizzahut_scraper import parse_pizza_hut_product_page
from src.scrapers.pizzahut_scraper import PizzaHutMenuScraper


class _FakeResponse:
    def __init__(self, html, status_code=200):
        self.status_code = status_code
        self.text = html
        self.content = html.encode("utf-8")

    def raise_for_status(self):
        return None


class _FakeSession:
    def __init__(self, pages):
        self.pages = pages
        self.headers = {}

    def get(self, url, timeout):
        if url not in self.pages:
            raise AssertionError(f"Unexpected URL: {url}")
        page = self.pages[url]
        return page if isinstance(page, _FakeResponse) else _FakeResponse(page)


class TestResearchWorkflow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "workflow.sqlite"
        initialize_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_public_menu_parser_pairs_only_explicit_sizes_and_prices(self):
        html = """
        <html><h1>Margarita</h1>
        <h2>Small 4 slices</h2><span>AED</span><strong>18</strong>
        <h2>Medium 6 slices</h2><span>AED</span><strong>28</strong>
        <h2>Large 8 slices</h2><span>AED</span><strong>39</strong>
        <h3>Also Available in</h3><span>Pan Pizza</span><span>Thin Crust Pizza</span>
        </html>
        """
        parsed = parse_pizza_hut_product_page(html)
        self.assertEqual([(x["normalized_size"], x["price"]) for x in parsed], [
            ("small", 18.0), ("medium", 28.0), ("large", 39.0),
        ])
        self.assertTrue(all(x["category_code"] == "pizza" for x in parsed))
        self.assertEqual(parsed[0]["available_crust_options"], ["Pan Pizza", "Thin Crust"])

    def test_public_menu_parser_does_not_infer_missing_price_or_crust(self):
        parsed = parse_pizza_hut_product_page(
            "<h1>Example Pizza</h1><h2>Small 4 slices</h2><span>Ask in store</span>"
        )
        self.assertEqual(parsed, [])

    def test_parser_handles_official_page_title_and_crust_alt_labels(self):
        parsed = parse_pizza_hut_product_page(
            "<title>Margarita</title><h2>Small 4 slices AED 18</h2>"
            "<h3>Also Available in:</h3><img alt='Pan Pizza'><img alt='Thin Crust Pizza'>"
        )
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["product_name"], "Margarita")
        self.assertEqual(parsed[0]["available_crust_options"], ["Pan Pizza", "Thin Crust"])

    def test_live_collector_saves_evidence_and_only_unverified_price_rows(self):
        catalog_url = PizzaHutMenuScraper.MENU_URL
        product_url = "https://www.pizzahut-me.com/content/margarita-country-AE"
        pages = {
            catalog_url: f"<html><a href='{product_url}'>Margarita</a></html>",
            product_url: """
                <html><title>Margarita</title>
                <h2>Medium 6 slices AED 28</h2>
                <h2>Large 8 slices AED 39</h2>
                <img alt="Pan Pizza"></html>
            """,
        }
        scraper = PizzaHutMenuScraper(
            db_path=self.db_path,
            session=_FakeSession(pages),
            evidence_dir=Path(self.temp_dir.name) / "captured_evidence",
        )
        result = scraper.run_live_extraction("DXB")
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["items_extracted"], 2)
        self.assertEqual(result["items_verified"], 0)

        conn = get_connection(self.db_path)
        rows = conn.execute(
            """SELECT po.original_price, po.verification_status, po.source_url,
                      po.collected_at, po.evidence_id, p.category_id, ev.file_path,
                      ev.file_hash_sha256, pv.normalized_size, pv.crust_type
               FROM price_observations po
               JOIN product_variants pv ON pv.id=po.product_variant_id
               JOIN products p ON p.id=pv.product_id
               JOIN evidence_records ev ON ev.id=po.evidence_id
               WHERE po.run_id=(SELECT id FROM research_runs WHERE run_uuid=?)""",
            (result["run_uuid"],),
        ).fetchall()
        conn.close()
        self.assertEqual({row["original_price"] for row in rows}, {28.0, 39.0})
        self.assertTrue(all(row["verification_status"] == "needs_review" for row in rows))
        self.assertTrue(all(row["source_url"] == product_url and row["collected_at"] for row in rows))
        self.assertTrue(all(Path(row["file_path"]).is_file() and row["file_hash_sha256"] for row in rows))
        self.assertTrue(all(row["crust_type"] == "Not stated on public menu" for row in rows))

    def test_http_gate_is_recorded_as_failed_run_with_response_evidence(self):
        scraper = PizzaHutMenuScraper(
            db_path=self.db_path,
            session=_FakeSession({PizzaHutMenuScraper.MENU_URL: _FakeResponse("Access denied", 403)}),
            evidence_dir=Path(self.temp_dir.name) / "captured_evidence",
        )
        result = scraper.run_live_extraction("DXB")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["items_extracted"], 0)
        self.assertIn("not bypassed", result["errors"][0])
        conn = get_connection(self.db_path)
        run = conn.execute("SELECT status, error_message FROM research_runs WHERE run_uuid=?", (result["run_uuid"],)).fetchone()
        evidence = conn.execute("SELECT http_status, file_hash_sha256 FROM evidence_records WHERE run_id=(SELECT id FROM research_runs WHERE run_uuid=?)", (result["run_uuid"],)).fetchone()
        conn.close()
        self.assertEqual(run["status"], "failed")
        self.assertIn("403", run["error_message"])
        self.assertEqual(evidence["http_status"], 403)
        self.assertTrue(evidence["file_hash_sha256"])

    def test_default_benchmark_seed_is_a_noop(self):
        self.assertEqual(seed_ground_truth_benchmarks(self.db_path), 0)
        self.assertEqual(get_all_benchmarks(self.db_path), [])

    def test_benchmark_requires_exact_captured_evidence_and_scores_missing(self):
        conn = get_connection(self.db_path)
        competitor_id = conn.execute("SELECT id FROM competitors WHERE code='pizza_hut'").fetchone()[0]
        channel_id = conn.execute("SELECT id FROM ordering_channels WHERE code='dine_in'").fetchone()[0]
        emirate_id = conn.execute("SELECT id FROM emirates WHERE code='DXB'").fetchone()[0]
        conn.close()

        source_url = "https://www.pizzahut-me.com/content/margarita-country-AE"
        capture_path = Path(self.temp_dir.name) / "margarita.html"
        capture_path.write_text("<html>Captured menu</html>", encoding="utf-8")
        capture_hash = hashlib.sha256(capture_path.read_bytes()).hexdigest()
        conn = get_connection(self.db_path)
        evidence_id = conn.execute(
            "INSERT INTO evidence_records (evidence_type, source_url, file_path, file_hash_sha256) VALUES ('html_snapshot', ?, ?, ?)",
            (source_url, str(capture_path), capture_hash),
        ).lastrowid
        conn.commit()
        conn.close()

        benchmark_id = add_verified_benchmark(
            competitor_id=competitor_id,
            product_name="Margarita",
            normalized_name="margherita",
            normalized_size="medium",
            channel_id=channel_id,
            emirate_id=emirate_id,
            expected_price=28,
            source_url=source_url,
            evidence_id=evidence_id,
            verified_by="Test reviewer",
            db_path=self.db_path,
        )
        self.assertTrue(next(b for b in get_all_benchmarks(self.db_path) if b["id"] == benchmark_id)["is_trusted"])
        result = AccuracyEngine(self.db_path).evaluate_collection_accuracy()
        self.assertEqual(result["missing_count"], 1)
        self.assertEqual(result["total_evaluated"], 0)
        self.assertIsNone(result["accuracy_percentage"])

    def test_benchmark_rejects_evidence_from_a_different_url(self):
        conn = get_connection(self.db_path)
        competitor_id = conn.execute("SELECT id FROM competitors WHERE code='pizza_hut'").fetchone()[0]
        channel_id = conn.execute("SELECT id FROM ordering_channels WHERE code='dine_in'").fetchone()[0]
        emirate_id = conn.execute("SELECT id FROM emirates WHERE code='DXB'").fetchone()[0]
        evidence_id = conn.execute(
            "INSERT INTO evidence_records (evidence_type, source_url, file_hash_sha256) VALUES ('html_snapshot', 'https://example.com/a', 'abc')"
        ).lastrowid
        conn.commit()
        conn.close()
        with self.assertRaises(ValueError):
            add_verified_benchmark(
                competitor_id=competitor_id, product_name="Margarita", normalized_name="margherita",
                normalized_size="medium", channel_id=channel_id, emirate_id=emirate_id,
                expected_price=28, source_url="https://example.com/b", evidence_id=evidence_id,
                verified_by="Test reviewer", db_path=self.db_path,
            )

    def test_review_revision_appends_without_overwriting_source_observation(self):
        repo = PizzaIntelligenceRepository(self.db_path)
        competitor = repo.get_competitor_by_code("pizza_hut")
        category = next(row for row in repo.get_all_categories() if row["code"] == "pizza")
        emirate = next(row for row in repo.get_all_emirates() if row["code"] == "DXB")
        channel = next(row for row in repo.get_all_channels() if row["code"] == "dine_in")
        platform = next(row for row in repo.get_all_platforms() if row["code"] == "direct_web")
        product_id = repo.get_or_create_product(competitor["id"], category["id"], "Margarita", "margherita")
        variant_id = repo.get_or_create_variant(product_id, "Medium", "medium", "Pan")
        source_url = "https://www.pizzahut-me.com/content/margarita-country-AE"
        capture_path = Path(self.temp_dir.name) / "revision.html"
        capture_path.write_text("<html>Reviewed menu</html>", encoding="utf-8")
        evidence_id = repo.save_evidence(
            source_url, evidence_type="html_snapshot", file_path=str(capture_path),
            file_hash_sha256=hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        )
        observation_id = repo.record_price_observation(
            competitor_id=competitor["id"], product_variant_id=variant_id,
            emirate_id=emirate["id"], channel_id=channel["id"], platform_id=platform["id"],
            original_price=28, source_url=source_url, evidence_id=evidence_id,
            verification_status="needs_review", data_origin="live_extraction",
        )

        revision_id = repo.append_observation_revision(
            observation_id, verification_status="verified", evidence_id=evidence_id,
            notes="Reviewed against the captured source page.",
        )
        conn = get_connection(self.db_path)
        original = conn.execute("SELECT original_price, verification_status FROM price_observations WHERE id=?", (observation_id,)).fetchone()
        revision = conn.execute("SELECT original_price, verification_status FROM price_observations WHERE id=?", (revision_id,)).fetchone()
        count = conn.execute("SELECT COUNT(*) FROM price_observations").fetchone()[0]
        conn.close()
        self.assertEqual(tuple(original), (28, "needs_review"))
        self.assertEqual(tuple(revision), (28, "verified"))
        self.assertEqual(count, 2)

    def test_quality_audit_flags_non_pizza_and_unreviewed_verified_labels(self):
        repo = PizzaIntelligenceRepository(self.db_path)
        competitor = repo.get_competitor_by_code("pizza_hut")
        category = next(row for row in repo.get_all_categories() if row["code"] == "pizza")
        emirate = next(row for row in repo.get_all_emirates() if row["code"] == "DXB")
        channel = next(row for row in repo.get_all_channels() if row["code"] == "dine_in")
        platform = next(row for row in repo.get_all_platforms() if row["code"] == "direct_web")
        product_id = repo.get_or_create_product(competitor["id"], category["id"], "Buffalo Wings", "buffalo_wings")
        variant_id = repo.get_or_create_variant(product_id, "Medium", "medium", "Pan")
        capture_path = Path(self.temp_dir.name) / "unreviewed-legacy.html"
        capture_path.write_text("<html>Unreviewed legacy capture</html>", encoding="utf-8")
        evidence_id = repo.save_evidence(
            "https://example.com/menu", evidence_type="html_snapshot",
            file_path=str(capture_path),
            file_hash_sha256=hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        )
        repo.record_price_observation(
            competitor_id=competitor["id"], product_variant_id=variant_id,
            emirate_id=emirate["id"], channel_id=channel["id"], platform_id=platform["id"],
            original_price=38, source_url="https://example.com/menu",
            evidence_id=evidence_id, verification_status="verified", data_origin="live_extraction",
        )
        audit = DatabaseValidator(self.db_path).validate_all()["checks"]["live_observation_quality"]
        self.assertEqual(audit["live_extraction_count"], 1)
        self.assertGreaterEqual(audit["suspect_count"], 1)
        self.assertEqual(audit["unreviewed_verified_labels"], 1)


if __name__ == "__main__":
    unittest.main()

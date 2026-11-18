"""Streamlit page and interaction smoke tests using an isolated SQLite copy."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import DEFAULT_DB_PATH as SOURCE_DB_PATH, PROJECT_ROOT
from streamlit.testing.v1 import AppTest

from src.db.repository import PizzaIntelligenceRepository


class TestStreamlitInteractions(unittest.TestCase):
    PAGES = [
        "📊 Executive Overview",
        "⚖️ Price & Gap Comparison",
        "📈 Historical Price Trends",
        "🛒 Channel Disparity & Markups",
        "🌐 Research & Live Collection",
        "📝 QA & Review Queue",
        "🗄️ Evidence Vault & Audit",
        "🏢 Catalog & Branch Manager",
        "🎁 Promotions & Deals Hub",
        "📑 Reports & Excel Export",
        "⚙️ System Status & Health",
    ]

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="pizza-streamlit-test-")
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "pizza_intelligence.db"
        shutil.copy2(SOURCE_DB_PATH, self.db_path)
        self._patches = [
            patch("config.DEFAULT_DB_PATH", self.db_path),
            patch("config.EVIDENCE_DIR", self.root / "evidence"),
            patch("src.db.connection.DEFAULT_DB_PATH", self.db_path),
            patch("src.db.connection.get_database_url", return_value=None),
        ]
        for patcher in self._patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.repo = PizzaIntelligenceRepository()
        self.app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30).run()

    def tearDown(self):
        self.temp_dir.cleanup()

    def navigate(self, page):
        navigation = next(item for item in self.app.radio if item.label == "Navigation")
        navigation.set_value(page)
        self.app.run()
        self.assertFalse([str(exc.value) for exc in self.app.exception])

    def test_all_navigation_routes_render(self):
        for page in self.PAGES:
            with self.subTest(page=page):
                self.navigate(page)

    def test_filters_search_export_and_empty_state_render(self):
        self.navigate("⚖️ Price & Gap Comparison")
        next(item for item in self.app.selectbox if item.label == "Select Pizza Size").set_value("large")
        next(item for item in self.app.selectbox if item.label == "Select Emirate").set_value(self.repo.get_all_emirates()[-1])
        next(item for item in self.app.selectbox if item.label == "Select Ordering Channel").set_value(self.repo.get_all_channels()[-1])
        self.app.run()
        self.assertFalse(self.app.exception)

        self.navigate("📊 Executive Overview")
        next(item for item in self.app.multiselect if item.label == "Filter by Competitor").set_value(
            [self.repo.get_all_competitors()[-1]["id"]]
        )
        next(item for item in self.app.text_input if item.label == "Search Recipe / Product").set_value("margherita")
        self.app.run()
        self.assertFalse(self.app.exception)

        self.navigate("📑 Reports & Excel Export")
        download = self.app.get("download_button")[0]
        download.click()
        self.app.run()
        self.assertTrue(download.value)
        csv_download = self.app.get("download_button")[1]
        csv_download.click()
        self.app.run()
        self.assertTrue(csv_download.value)
        self.assertFalse(self.app.exception)

        self.navigate("🗄️ Evidence Vault & Audit")
        with self.repo._get_connection() as conn:
            candidates = conn.execute(
                "SELECT id, file_path FROM evidence_records WHERE file_hash_sha256 IS NOT NULL ORDER BY id"
            ).fetchall()
        artifact_id = next(int(row["id"]) for row in candidates if row["file_path"] and Path(row["file_path"]).is_file())
        next(item for item in self.app.selectbox if item.label == "Select Evidence Record to Inspect").set_value(artifact_id)
        self.app.run()
        evidence_download = self.app.get("download_button")[0]
        evidence_download.click()
        self.app.run()
        self.assertTrue(evidence_download.value)
        self.assertFalse(self.app.exception)

        self.navigate("🎁 Promotions & Deals Hub")
        next(item for item in self.app.selectbox if item.label == "Filter by Brand").set_value(
            self.repo.get_all_competitors()[-1]
        )
        next(item for item in self.app.selectbox if item.label == "Filter by Promo Type").set_value("combo")
        self.app.run()
        self.assertFalse(self.app.exception)

    def test_invalid_form_validation_and_reference_refresh(self):
        self.navigate("🌐 Research & Live Collection")
        submit = next(item for item in self.app.form_submit_button if item.label == "Record Observation for QA")
        submit.click()
        self.app.run()
        self.assertTrue(any("Source URL is strictly mandatory" in item.value for item in self.app.error))

        self.navigate("⚙️ System Status & Health")
        refresh = next(item for item in self.app.button if item.label == "Refresh master reference data")
        refresh.click()
        self.app.run()
        self.assertFalse(self.app.exception)
        self.assertEqual(len(self.repo.get_all_emirates()), 7)

    def test_run_now_persists_mocked_collector_result(self):
        import requests

        product_url = "https://www.pizzahut-me.com/content/margarita-country-AE"

        def fake_get(_session, url, timeout=20, **kwargs):
            html = (
                f'<html><a href="{product_url}">Margarita</a></html>'
                if url.endswith("pizzas-country-AE")
                else "<html><h1>Margarita</h1><p>Medium 6 slices AED 28</p></html>"
            )
            return type("FakeResponse", (), {
                "status_code": 200,
                "text": html,
                "content": html.encode("utf-8"),
                "headers": {},
            })()

        with patch.object(requests.Session, "get", fake_get):
            self.navigate("🌐 Research & Live Collection")
            run_now = next(item for item in self.app.button if item.label.startswith("Run now"))
            run_now.click()
            self.app.run()

        runs = self.repo.get_research_runs(limit=1)
        self.assertEqual(runs[0]["status"], "completed")
        self.assertEqual(runs[0]["items_extracted"], 1)
        self.assertEqual(runs[0]["items_verified"], 0)
        self.assertEqual(runs[0]["error_message"], None)
        self.assertFalse(self.app.exception)


if __name__ == "__main__":
    unittest.main()

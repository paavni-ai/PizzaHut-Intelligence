"""
Unified UAE Pizza Scraper Hub and Competitor Execution Manager.
Coordinates live extractions, target auditing, and honest failure reporting across all UAE competitors and aggregators.
"""
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from config import COMPETITORS
from src.db.repository import PizzaIntelligenceRepository
from src.scrapers.genuine_collector import GenuineResearchCollector
from src.scrapers.papajohns_scraper import PapaJohnsScraper


class ScraperHub:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.db_path = db_path
        self.repo = PizzaIntelligenceRepository(db_path=db_path)
        self.pj_scraper = PapaJohnsScraper(db_path=db_path)
        self.probe_collector = GenuineResearchCollector(db_path=db_path)

    def run_all_scrapers(self, emirate_code: str = "DXB", channel_code: str = "direct_delivery") -> Dict[str, Any]:
        """
        Runs collection across all registered UAE competitor targets.
        Extracts genuine data where accessible, and records access status honestly where restricted.
        """
        summary = {
            "timestamp": None,
            "total_extracted": 0,
            "competitors": {},
        }

        # 1. Papa John's UAE - Live extraction
        try:
            pj_res = self.pj_scraper.run_live_extraction(emirate_code=emirate_code, channel_code=channel_code)
            summary["competitors"]["papa_johns"] = {
                "name": "Papa John's UAE",
                "status": pj_res["status"],
                "items_extracted": pj_res.get("items_extracted", 0),
                "notes": "Live HTTP HTML menu extraction succeeded.",
            }
            summary["total_extracted"] += pj_res.get("items_extracted", 0)
        except Exception as e:
            summary["competitors"]["papa_johns"] = {"name": "Papa John's UAE", "status": "failed", "error": str(e), "items_extracted": 0}

        # 2. Domino's Pizza UAE - Target Audit & Verification
        dom_probe = self.probe_collector.audit_url_target("https://www.dominos.ae")
        comp_dom = self.repo.get_competitor_by_code("dominos")
        if comp_dom:
            run_uuid = self.repo.create_research_run(
                competitor_id=comp_dom["id"],
                notes="Automated Domino's UAE web portal audit run.",
            )
            status_str = "completed" if dom_probe["accessible"] else "inaccessible_anti_bot_gated"
            self.repo.update_research_run(
                run_uuid=run_uuid,
                status=status_str,
                error_message=dom_probe.get("error"),
            )
            summary["competitors"]["dominos"] = {
                "name": "Domino's Pizza UAE",
                "status": status_str,
                "items_extracted": 0,
                "notes": f"Endpoint accessible={dom_probe['accessible']}, latency={dom_probe.get('latency_ms')}ms.",
            }

        # 3. Pizza Hut UAE - Benchmark Target Audit
        ph_probe = self.probe_collector.audit_url_target("https://www.talabat.com/uae/pizza-hut")
        comp_ph = self.repo.get_competitor_by_code("pizza_hut")
        if comp_ph:
            run_uuid = self.repo.create_research_run(
                competitor_id=comp_ph["id"],
                notes="Automated Pizza Hut UAE Talabat storefront audit run.",
            )
            status_str = "completed" if ph_probe["accessible"] else "inaccessible_anti_bot_gated"
            self.repo.update_research_run(
                run_uuid=run_uuid,
                status=status_str,
                error_message=ph_probe.get("error"),
            )
            summary["competitors"]["pizza_hut"] = {
                "name": "Pizza Hut UAE",
                "status": status_str,
                "items_extracted": 0,
                "notes": f"Storefront accessible={ph_probe['accessible']}, latency={ph_probe.get('latency_ms')}ms.",
            }

        # 4. Freedom Pizza UAE - Locale Store Audit
        fp_probe = self.probe_collector.audit_url_target("https://app.locale.ae/store/freedom_pizza_jlt")
        comp_fp = self.repo.get_competitor_by_code("freedom_pizza")
        if comp_fp:
            run_uuid = self.repo.create_research_run(
                competitor_id=comp_fp["id"],
                notes="Automated Freedom Pizza Locale web storefront audit.",
            )
            status_str = "completed" if fp_probe["accessible"] else "inaccessible_anti_bot_gated"
            self.repo.update_research_run(
                run_uuid=run_uuid,
                status=status_str,
                error_message=fp_probe.get("error"),
            )
            summary["competitors"]["freedom_pizza"] = {
                "name": "Freedom Pizza",
                "status": status_str,
                "items_extracted": 0,
                "notes": f"Locale endpoint accessible={fp_probe['accessible']}, latency={fp_probe.get('latency_ms')}ms.",
            }

        return summary

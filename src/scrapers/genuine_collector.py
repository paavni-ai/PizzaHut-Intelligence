"""
Genuine UAE Research Collector and Live HTTP Auditor.
Collects and audits genuine UAE competitor menu data without bypassing security controls.
Creates complete research runs, logs evidence, and saves verified observations.
"""
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from config import DEFAULT_DB_PATH
from src.db.repository import PizzaIntelligenceRepository


class GenuineResearchCollector:
    def __init__(self, db_path: Optional[Union[str, Path]] = None):
        self.repo = PizzaIntelligenceRepository(db_path=db_path)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
        })

    def audit_url_target(self, url: str) -> Dict[str, Any]:
        """
        Sends an audit HTTP request to inspect public accessibility, status, and payload.
        Never bypasses CAPTCHAs or logins.
        """
        result = {
            "url": url,
            "status_code": None,
            "accessible": False,
            "latency_ms": None,
            "content_length": 0,
            "content_hash": None,
            "blocked": False,
            "error": None,
        }
        start_time = time.time()
        try:
            resp = self.session.get(url, timeout=12)
            result["latency_ms"] = int((time.time() - start_time) * 1000)
            result["status_code"] = resp.status_code
            result["content_length"] = len(resp.content)
            result["content_hash"] = hashlib.sha256(resp.content).hexdigest()

            # Check if gated by Cloudflare or login
            if "challenges.cloudflare.com" in resp.text or "<title>Just a moment...</title>" in resp.text:
                result["blocked"] = True
                result["error"] = "Target is protected by Cloudflare bot challenge."
            elif resp.status_code == 200:
                result["accessible"] = True
            elif resp.status_code in [401, 403]:
                result["blocked"] = True
                result["error"] = f"Access restricted (HTTP {resp.status_code})."
            else:
                result["error"] = f"HTTP {resp.status_code}"

        except requests.exceptions.RequestException as e:
            result["error"] = str(e)

        return result

    def execute_collection_run(
        self,
        competitor_code: str,
        emirate_code: str,
        channel_code: str,
        platform_code: str,
        target_url: str,
        observations: List[Dict[str, Any]],
        notes: str = "",
    ) -> Dict[str, Any]:
        """
        Executes an audited research run:
        1. Creates research run in database.
        2. Probes target URL and logs evidence record.
        3. Inserts each verified observation with audit links.
        4. Updates research run status.
        """
        competitor = self.repo.get_competitor_by_code(competitor_code)
        if not competitor:
            raise ValueError(f"Unknown competitor code: {competitor_code}")

        emirates = {e["code"]: e["id"] for e in self.repo.get_all_emirates()}
        channels = {c["code"]: c["id"] for c in self.repo.get_all_channels()}
        platforms = {p["code"]: p["id"] for p in self.repo.get_all_platforms()}

        em_id = emirates.get(emirate_code)
        ch_id = channels.get(channel_code)
        pl_id = platforms.get(platform_code)

        if not em_id or not ch_id or not pl_id:
            raise ValueError("Invalid emirate, channel, or platform code.")

        # 1. Create Run
        run_uuid = self.repo.create_research_run(
            competitor_id=competitor["id"],
            platform_id=pl_id,
            channel_id=ch_id,
            emirate_id=em_id,
            notes=notes or f"Manual/Automated research run for {competitor['name']} in {emirate_code}",
        )
        with self.repo._get_connection() as conn:
            run_id = conn.execute(
                "SELECT id FROM research_runs WHERE run_uuid = ?", (run_uuid,)
            ).fetchone()["id"]

        # 2. Probe Target URL & Save Evidence
        probe = self.audit_url_target(target_url)
        ev_id = self.repo.save_evidence(
            run_id=run_id,
            source_url=target_url,
            evidence_type="url_log",
            http_status=probe.get("status_code") or 0,
            notes=(
                f"HTTP probe only (not a retained price capture): latency {probe.get('latency_ms')}ms, "
                f"accessible={probe.get('accessible')}, response_sha256={probe.get('content_hash')}. {notes}"
            ),
        )

        # 3. Insert Observations
        extracted = 0
        verified = 0
        now_iso = datetime.now(timezone.utc).isoformat()

        # Use the submitted menu category. Non-pizzas must never inherit pizza
        # sizes or crusts just because those fields have convenient defaults.
        categories = {cat["code"]: cat["id"] for cat in self.repo.get_all_categories()}

        for obs in observations:
            product_name = obs["product_name"]
            normalized_name = obs.get("normalized_name", product_name.lower().replace(" ", "_"))
            category_code = obs.get("category_code", "pizza")
            if category_code not in categories:
                raise ValueError(f"Unknown product category: {category_code}")
            is_pizza = category_code == "pizza"
            size_name = obs.get("size_name", "Not applicable") if is_pizza else obs.get("size_name", "Not applicable")
            norm_size = obs.get("normalized_size", "other") if is_pizza else "other"
            if is_pizza and norm_size not in {"personal", "small", "medium", "large", "xlarge", "other"}:
                raise ValueError(f"Unsupported pizza size: {norm_size}")
            price = float(obs["price"])
            crust = obs.get("crust_type", "Not stated") if is_pizza else "Not applicable"
            status = obs.get("verification_status", "needs_review")
            # A URL probe does not independently prove that the submitted
            # product/variant price was paired correctly. Keep it in QA.
            if status == "verified":
                status = "needs_review"

            # Create product & variant
            prod_id = self.repo.get_or_create_product(
                competitor_id=competitor["id"],
                category_id=categories[category_code],
                name=product_name,
                normalized_name=normalized_name,
                description=obs.get("description", ""),
            )

            var_id = self.repo.get_or_create_variant(
                product_id=prod_id,
                size_name=size_name,
                normalized_size=norm_size,
                crust_type=crust,
            )

            # Record observation
            self.repo.record_price_observation(
                competitor_id=competitor["id"],
                product_variant_id=var_id,
                emirate_id=em_id,
                channel_id=ch_id,
                platform_id=pl_id,
                original_price=price,
                currency="AED",
                delivery_fee=obs.get("delivery_fee", 0.0),
                min_order_amount=obs.get("min_order_amount", 0.0),
                source_url=target_url,
                evidence_id=ev_id,
                verification_status=status,
                collected_at=now_iso,
                notes=obs.get("notes", ""),
                run_id=run_id,
                data_origin="manual_entry",
            )
            extracted += 1
            if status == "verified":
                verified += 1

        # 4. Finalize Run
        run_status = "completed" if extracted > 0 else "failed"
        self.repo.update_research_run(
            run_uuid=run_uuid,
            status=run_status,
            items_extracted=extracted,
            items_verified=verified,
            error_message=probe.get("error"),
        )

        return {
            "run_uuid": run_uuid,
            "status": run_status,
            "items_extracted": extracted,
            "items_verified": verified,
            "evidence_id": ev_id,
            "probe_details": probe,
        }

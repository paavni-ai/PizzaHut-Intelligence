"""Public Pizza Hut UAE menu collector.

This collector reads the public Pizza Hut Middle East UAE menu only. It does not
place orders, select a branch, or bypass login / anti-bot restrictions. Extracted
prices stay in the human review queue because the public catalog does not prove
branch availability, ordering channel, or checkout price.
"""
import hashlib
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin, urlparse

import requests

from config import EVIDENCE_DIR
from src.db.repository import PizzaIntelligenceRepository


class _MenuHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text: List[str] = []
        self.links: List[str] = []
        self.h1_parts: List[str] = []
        self._in_h1 = False
        self.title_parts: List[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "h1":
            self._in_h1 = True
        if tag.lower() == "title" and not self.title_parts:
            self._in_title = True
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)
        if tag.lower() == "img":
            alt = dict(attrs).get("alt")
            if alt and alt.strip():
                self.text.append(" ".join(alt.split()))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "h1":
            self._in_h1 = False
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        normalized = " ".join(data.split())
        if normalized:
            self.text.append(normalized)
            if self._in_h1:
                self.h1_parts.append(normalized)
            if self._in_title:
                self.title_parts.append(normalized)


def parse_pizza_hut_product_page(html: str) -> List[Dict[str, Any]]:
    """Extract only explicitly paired Small/Medium/Large AED prices."""
    parser = _MenuHTMLParser()
    parser.feed(html)
    page_text = " ".join(parser.text)
    product_name = " ".join(parser.h1_parts).strip() or " ".join(parser.title_parts).strip()
    if not product_name:
        return []

    lowered_text = page_text.casefold()
    crust_options: List[str] = []
    if "also available in" in lowered_text:
        option_text = lowered_text.split("also available in", 1)[1].split("recommended products", 1)[0]
        for label in ("MIA Pizza", "Pan Pizza", "Thin Crust", "Stuffed Crust"):
            if label.casefold() in option_text:
                crust_options.append(label)

    variants: List[Dict[str, Any]] = []
    seen = set()
    pattern = re.compile(
        r"\b(Small|Medium|Large)\s+(\d+)\s+slices?\s+AED\s*([0-9]+(?:\.[0-9]{1,2})?)\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(page_text):
        size = match.group(1).lower()
        price = float(match.group(3))
        if (size, price) in seen:
            continue
        seen.add((size, price))
        variants.append({
            "product_name": product_name,
            "normalized_name": normalize_pizza_name(product_name),
            "size_name": size.title(),
            "normalized_size": size,
            "slices_count": int(match.group(2)),
            "price": price,
            "category_code": "pizza",
            "crust_type": "Not stated on public menu",
            "available_crust_options": crust_options,
        })
    return variants


def normalize_pizza_name(name: str) -> str:
    """Normalize known Pizza Hut menu names conservatively; otherwise slug exact name."""
    lowered = name.casefold()
    aliases = {
        "margarita": "margherita",
        "margherita": "margherita",
        "classic pepperoni": "pepperoni",
        "pepperoni": "pepperoni",
        "super supreme": "super_supreme",
        "veggie lover": "veggie",
        "chicken bbq": "bbq_chicken",
        "bbq chicken": "bbq_chicken",
    }
    for label, normalized in aliases.items():
        if label in lowered:
            return normalized
    return re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")


class PizzaHutMenuScraper:
    MENU_URL = "https://www.pizzahut-me.com/fullmenu/pizzas-country-AE"
    HOST = "www.pizzahut-me.com"

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        session=None,
        evidence_dir: Optional[Union[str, Path]] = None,
    ):
        self.repo = PizzaIntelligenceRepository(db_path=db_path)
        self.session = session or requests.Session()
        self.evidence_dir = Path(evidence_dir) if evidence_dir else EVIDENCE_DIR
        self.session.headers.update({
            "User-Agent": "PizzaHut-Intelligence/1.0 (public menu research; contact via repository owner)",
            "Accept": "text/html,application/xhtml+xml",
        })

    @staticmethod
    def _safe_product_links(html: str, page_url: str) -> List[str]:
        parser = _MenuHTMLParser()
        parser.feed(html)
        links = []
        for href in parser.links:
            url = urljoin(page_url, href)
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname != PizzaHutMenuScraper.HOST:
                continue
            if "/fullmenu/" in parsed.path or not parsed.path.endswith("country-AE"):
                continue
            if not (parsed.path.startswith("/pizzas/") or parsed.path.startswith("/content/")):
                continue
            if url not in links:
                links.append(url)
        return links

    def _capture(self, run_id: int, url: str, content: bytes, http_status: int) -> int:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(content).hexdigest()
        filename = f"pizzahut_{digest[:20]}.html"
        path = self.evidence_dir / filename
        if not path.exists():
            path.write_bytes(content)
        return self.repo.save_evidence(
            run_id=run_id,
            source_url=url,
            evidence_type="html_snapshot",
            file_path=str(path),
            file_hash_sha256=digest,
            http_status=http_status,
            notes="Captured from the public Pizza Hut UAE regional menu; prices require branch/channel review.",
        )

    def _capture_http_failure(self, run_id: int, url: str, response) -> None:
        """Retain an auditable response snapshot even when the source rejects us."""
        try:
            self._capture(run_id, url, response.content, response.status_code)
        except Exception:
            # Preserve the collection failure as a run error if evidence storage
            # itself is unavailable; never hide the original HTTP status.
            pass

    @staticmethod
    def _http_failure(response) -> str:
        if response.status_code in (401, 403, 429):
            reason = "authentication, anti-bot, or rate-limit gate; not bypassed"
        else:
            reason = "HTTP request rejected"
        return f"HTTP {response.status_code}: {reason}"

    def run_live_extraction(self, emirate_code: str = "DXB") -> Dict[str, Any]:
        competitor = self.repo.get_competitor_by_code("pizza_hut")
        if not competitor:
            raise ValueError("Pizza Hut competitor record is missing.")
        emirates = {row["code"]: row["id"] for row in self.repo.get_all_emirates()}
        channels = {row["code"]: row["id"] for row in self.repo.get_all_channels()}
        platforms = {row["code"]: row["id"] for row in self.repo.get_all_platforms()}
        categories = {row["code"]: row["id"] for row in self.repo.get_all_categories()}
        if emirate_code not in emirates or "dine_in" not in channels or "direct_web" not in platforms or "pizza" not in categories:
            raise ValueError("Required Pizza Hut market, channel, platform, or category reference is missing.")

        run_uuid = self.repo.create_research_run(
            competitor_id=competitor["id"],
            platform_id=platforms["direct_web"],
            channel_id=channels["dine_in"],
            emirate_id=emirates[emirate_code],
            notes="Public regional menu extraction. Branch-specific ordering prices require human confirmation.",
        )
        with self.repo._get_connection() as conn:
            run_row = conn.execute("SELECT id FROM research_runs WHERE run_uuid = ?", (run_uuid,)).fetchone()
            run_id = run_row["id"]

        started = time.time()
        extracted = 0
        errors: List[str] = []
        catalog_evidence = None
        try:
            response = self.session.get(self.MENU_URL, timeout=20)
            if response.status_code >= 400:
                self._capture_http_failure(run_id, self.MENU_URL, response)
                raise requests.HTTPError(self._http_failure(response), response=response)
            catalog_evidence = self._capture(run_id, self.MENU_URL, response.content, response.status_code)
            product_urls = self._safe_product_links(response.text, self.MENU_URL)
            if not product_urls:
                errors.append("No UAE pizza product links found on the public menu page.")

            for product_url in product_urls:
                try:
                    product_response = self.session.get(product_url, timeout=20)
                    if product_response.status_code >= 400:
                        self._capture_http_failure(run_id, product_url, product_response)
                        raise requests.HTTPError(self._http_failure(product_response), response=product_response)
                    evidence_id = self._capture(run_id, product_url, product_response.content, product_response.status_code)
                    variants = parse_pizza_hut_product_page(product_response.text)
                    if not variants:
                        errors.append(f"No explicit size/price pairs found at {product_url}")
                        continue
                    for item in variants:
                        product_id = self.repo.get_or_create_product(
                            competitor["id"], categories["pizza"], item["product_name"],
                            item["normalized_name"],
                        )
                        variant_id = self.repo.get_or_create_variant(
                            product_id, item["size_name"], item["normalized_size"],
                            item["crust_type"], slices_count=item["slices_count"],
                        )
                        self.repo.record_price_observation(
                            competitor_id=competitor["id"],
                            product_variant_id=variant_id,
                            emirate_id=emirates[emirate_code],
                            channel_id=channels["dine_in"],
                            platform_id=platforms["direct_web"],
                            original_price=item["price"],
                            source_url=product_url,
                            evidence_id=evidence_id,
                            run_id=run_id,
                            verification_status="needs_review",
                            collected_at=datetime.now(timezone.utc).isoformat(),
                            data_origin="live_extraction",
                            notes=(
                                "Public regional menu price; confirm branch, channel, crust, and checkout applicability before QA approval. "
                                + (
                                    "Crust options listed on page (prices not stated separately): "
                                    + ", ".join(item["available_crust_options"]) + "."
                                    if item["available_crust_options"] else ""
                                )
                            ),
                        )
                        extracted += 1
                except requests.RequestException as exc:
                    errors.append(f"{product_url}: {exc}")
                except Exception as exc:
                    errors.append(f"{product_url}: processing failed ({type(exc).__name__})")
        except requests.RequestException as exc:
            errors.append(str(exc))
        except Exception as exc:
            errors.append(f"Catalog processing failed ({type(exc).__name__})")

        final_status = "completed" if extracted and not errors else ("partial" if extracted else "failed")
        self.repo.update_research_run(
            run_uuid=run_uuid,
            status=final_status,
            items_extracted=extracted,
            items_verified=0,
            error_message="; ".join(errors) if errors else None,
        )
        return {
            "run_uuid": run_uuid,
            "status": final_status,
            "items_extracted": extracted,
            "items_verified": 0,
            "catalog_evidence_id": catalog_evidence,
            "elapsed_ms": int((time.time() - started) * 1000),
            "errors": errors,
        }

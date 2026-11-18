"""Menu Mapping & Price Comparison, using real stored research and imports."""
import calendar
import csv
import io
from datetime import date, timedelta
from typing import Any, Mapping, Optional, Sequence

import altair as alt
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.menu_mapping.integrations import integration_for
from src.menu_mapping.service import (
    PROMOTION_TYPES,
    approve_menu_match,
    calculate_cart_quotes,
    get_approved_menu_matches,
    get_canonical_variants,
    get_comparison_history,
    get_latest_comparison_prices,
    get_latest_fee_observations,
    get_menu_import_content,
    get_promotion_records,
    get_recent_menu_imports,
    get_unmatched_menu_items,
    get_unverified_menu_prices,
    import_menu_csv,
    parse_menu_upload,
    promotion_status,
    reject_menu_match,
    save_cart_comparison,
    save_fee_observation,
    save_promotion,
    verify_menu_price,
)
from src.ui.styles import render_brand_header

_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_PROMOTION_LABELS = {
    "percentage_discount": "Percentage discount", "fixed_discount": "Fixed amount discount",
    "bogo": "Buy one, get one", "free_delivery": "Free delivery", "pizza_deal": "Pizza deal",
    "meal_deal": "Meal deal", "combo_offer": "Combo offer", "platform_discount": "Platform discount",
    "minimum_spend": "Minimum spend", "first_order": "First-order offer", "loyalty": "Loyalty offer", "other": "Other",
}


def _default_competitor(competitors: Sequence[Mapping[str, Any]]) -> int:
    return next((c["id"] for c in competitors if c["code"] == "pizza_hut"), competitors[0]["id"])


def _comparison_groups(
    rows: Sequence[Mapping[str, Any]], platforms: Sequence[Mapping[str, Any]], history: Sequence[Mapping[str, Any]] = ()
) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (row["competitor_id"], row["emirate_id"], row.get("location_id"), row["product_variant_id"])
        group = groups.setdefault(key, {
            "Brand": row["competitor_name"], "Item": row["item_name"], "Category": row["category_name"],
            "Size": row["size_name"], "Crust": row["crust_type"], "Emirate": row["emirate_name"],
            "Location": row.get("location_name") or "Not recorded", "_prices": {},
            "_variant_id": row["product_variant_id"], "_emirate_id": row["emirate_id"],
            "_location_id": row.get("location_id"), "_competitor_id": row["competitor_id"],
        })
        group["_prices"][row["platform_id"]] = row
    result = []
    for group in groups.values():
        prices = []
        for platform in platforms:
            row = group["_prices"].get(platform["id"])
            group[f"{platform['name']} (AED)"] = float(row["price"]) if row and row.get("price") is not None else None
            group[f"{platform['name']} status"] = row["verification_status"] if row else "No record"
            if row and row.get("price") is not None:
                prices.append((float(row["price"]), platform["name"], row))
        if prices:
            values = [item[0] for item in prices]
            low, high = min(values), max(values)
            group["Price gap (AED)"] = round(high - low, 2) if len(values) > 1 else None
            group["Price gap (%)"] = round((high - low) / low * 100, 1) if len(values) > 1 and low > 0 else None
            group["Cheapest recorded"] = min(prices, key=lambda item: item[0])[1] if len(prices) > 1 else "—"
            group["Most expensive recorded"] = max(prices, key=lambda item: item[0])[1] if len(prices) > 1 else "—"
            group["Last updated"] = max(str(row["observed_at"]) for _, _, row in prices)
            group["Source status"] = "; ".join(f"{name}: {row['verification_status']}" for _, name, row in prices)
        else:
            group["Price gap (AED)"] = None
            group["Price gap (%)"] = None
            group["Cheapest recorded"] = "—"
            group["Most expensive recorded"] = "—"
            group["Last updated"] = None
            group["Source status"] = "No price observations"
        trends = []
        for platform_id, current in group["_prices"].items():
            series = [h for h in history if h.get("competitor_id") == group["_competitor_id"]
                      and h.get("platform_id") == platform_id
                      and h.get("product_variant_id") == group["_variant_id"]
                      and h.get("emirate_id") == group["_emirate_id"]
                      and h.get("location_id") == group["_location_id"]]
            series.sort(key=lambda h: str(h["observed_at"]))
            prior = next((h for h in reversed(series) if str(h["observed_at"]) < str(current["observed_at"])), None)
            if prior and prior.get("price") is not None and current.get("price") is not None:
                change = float(current["price"]) - float(prior["price"])
                if abs(change) >= 0.005:
                    label = next((p["name"] for p in platforms if p["id"] == platform_id), str(platform_id))
                    trends.append(f"{label} {'↑' if change > 0 else '↓'} {change:+.2f} AED")
        group["Recent change"] = "; ".join(trends) if trends else "No prior comparison"
        result.append(group)
    return result


def _make_csv_template() -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerow([
        "item_name", "category", "size_name", "price", "availability", "crust_type",
        "ingredients", "description", "external_id", "source_url", "observed_at",
    ])
    return buffer.getvalue().encode("utf-8")


def _optional_amount(label: str, key: str) -> Optional[float]:
    raw = st.text_input(label, key=key).strip()
    if not raw:
        return None
    try:
        amount = float(raw)
    except ValueError as exc:
        raise ValueError(f"{label} must be a non-negative AED amount or blank if unknown.") from exc
    if amount < 0:
        raise ValueError(f"{label} cannot be negative.")
    return amount


def _evidence_upload(label: str, key: str):
    uploaded = st.file_uploader(label, type=["png", "jpg", "jpeg", "webp", "html", "htm"], key=key)
    return (uploaded.getvalue(), uploaded.name) if uploaded else (None, None)


def _render_dashboard(repo, competitors, platforms, selected_competitor):
    rows = [r for r in get_latest_comparison_prices(repo.db_path) if r["competitor_id"] == selected_competitor]
    history = [r for r in get_comparison_history(repo.db_path) if r["competitor_id"] == selected_competitor]
    groups = _comparison_groups(rows, platforms, history)
    paired = [g for g in groups if g["Price gap (AED)"] is not None]
    wins: dict[str, int] = {}
    for group in paired:
        wins[group["Cheapest recorded"]] = wins.get(group["Cheapest recorded"], 0) + 1
    cheapest = max(wins, key=wins.get) if wins else "—"
    promotions = [p for p in get_promotion_records(repo.db_path) if p["competitor_id"] == selected_competitor]
    statuses = {p["id"]: promotion_status(p) for p in promotions}
    active = [p for p in promotions if statuses[p["id"]] == "Active"]
    expiring = []
    today = date.today()
    for promo in active:
        try:
            days_left = (date.fromisoformat(str(promo["ends_at"])[:10]) - today).days if promo.get("ends_at") else None
        except ValueError:
            days_left = None
        if days_left is not None and 0 <= days_left <= 7:
            expiring.append(promo)
    approved_count = len(get_approved_menu_matches(repo.db_path))
    recorded_platform_ids = {r["platform_id"] for r in rows}
    last_updated = max((str(r["observed_at"]) for r in rows), default="No observations")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Approved external mappings", approved_count)
    c2.metric("Items with recorded price gaps", len(paired))
    c3.metric("Most frequent recorded lowest price", cheapest)
    c4.metric("Mean observed price gap", f"AED {sum(g['Price gap (AED)'] for g in paired)/len(paired):.2f}" if paired else "—")
    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Verified active promotions", len(active))
    c6.metric("Verified promotions expiring in 7 days", len(expiring))
    c7.metric("Platforms with price records", len(recorded_platform_ids))
    c8.metric("Latest stored observation", last_updated[:19] if last_updated != "No observations" else last_updated)
    st.caption("Metrics use stored observations only. Price records keep their verification status; unmatched platforms have no fabricated price.")

    if rows:
        st.subheader("Latest Pizza Hut menu prices")
        price_table = pd.DataFrame(rows).rename(columns={
            "platform_name": "Platform", "item_name": "Item", "category_name": "Category",
            "size_name": "Size", "crust_type": "Crust", "emirate_name": "Emirate",
            "location_name": "Location", "price": "Price (AED)",
            "verification_status": "Verification", "observed_at": "Last collected",
            "source_url": "Source",
        })
        price_columns = ["Platform", "Item", "Category", "Size", "Crust", "Emirate",
                         "Location", "Price (AED)", "Verification", "Last collected", "Source"]
        price_table = price_table[price_columns].sort_values("Last collected", ascending=False)
        st.dataframe(
            price_table,
            column_config={"Source": st.column_config.LinkColumn("Source", display_text="Open source")},
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Prices link to their recorded source and retain their verification state. Empty prices and unmonitored platforms are not estimated.")

        df = pd.DataFrame(rows)
        avg = df.dropna(subset=["price"]).groupby("platform_name", as_index=False)["price"].mean().rename(columns={"price": "Average AED"})
        st.subheader("Average latest recorded item prices")
        if not avg.empty:
            st.altair_chart(
                alt.Chart(avg).mark_bar().encode(
                    x=alt.X("platform_name:N", title="Platform", sort="-y"),
                    y=alt.Y("Average AED:Q", title="AED"),
                    tooltip=["platform_name", alt.Tooltip("Average AED:Q", format=".2f")],
                    color=alt.Color("platform_name:N", legend=None),
                ).properties(height=260), use_container_width=True,
            )
        else:
            st.info("No prices are available for this chart.")
    else:
        st.info("No platform price observations are stored for this brand yet.")

    if paired:
        gap_df = pd.DataFrame(paired).groupby("Category", as_index=False)["Price gap (AED)"].mean()
        st.subheader("Average recorded price gap by category")
        st.altair_chart(
            alt.Chart(gap_df).mark_bar().encode(
                x=alt.X("Category:N", sort="-y"), y=alt.Y("Price gap (AED):Q", title="Mean gap (AED)"),
                tooltip=["Category", alt.Tooltip("Price gap (AED):Q", format=".2f")],
                color=alt.Color("Category:N", legend=None),
            ).properties(height=240), use_container_width=True,
        )

    if active:
        st.subheader("Verified active promotions")
        promo_table = pd.DataFrame([
            {"Promotion": p["title"], "Platform": p.get("platform_name") or "Not specified",
             "Offer": _PROMOTION_LABELS.get(p.get("promotion_type") or p["promo_type"], p["promo_type"]),
             "Ends": p.get("ends_at") or "No end date recorded", "Source": p["source_url"]}
            for p in active
        ])
        st.dataframe(
            promo_table,
            column_config={"Source": st.column_config.LinkColumn("Source", display_text="Open source")},
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No promotion is currently marked active with recent source verification.")

    schedule = [(promo, day) for promo in active for day in promo.get("weekdays", [])]
    if schedule:
        count_by_platform: dict[str, int] = {}
        count_by_day: dict[str, int] = {day: 0 for day in _DAYS}
        for promo, day in schedule:
            platform = promo.get("platform_name") or "All platforms"
            count_by_platform[platform] = count_by_platform.get(platform, 0) + 1
            count_by_day[_DAYS[day]] += 1
        d1, d2 = st.columns(2)
        with d1:
            st.subheader("Verified promotion frequency by platform")
            st.bar_chart(pd.DataFrame([{"Platform": k, "Scheduled days": v} for k, v in count_by_platform.items()]).set_index("Platform"))
        with d2:
            st.subheader("Verified weekly promotion activity")
            st.bar_chart(pd.DataFrame([{"Day": day, "Promotions": count_by_day[day]} for day in _DAYS]).set_index("Day"))
    else:
        st.info("No verified weekday schedules are stored yet; legacy promotion rows are not assigned invented days.")

    if history:
        trend = pd.DataFrame(history)
        trend["day"] = pd.to_datetime(trend["observed_at"], errors="coerce", utc=True).dt.date
        trend = trend.dropna(subset=["day", "price"])
        if not trend.empty:
            trend = trend.groupby(["day", "platform_name"], as_index=False)["price"].median()
            st.subheader("Historical median item prices")
            st.altair_chart(
                alt.Chart(trend).mark_line(point=True).encode(
                    x=alt.X("day:T", title="Recorded day"), y=alt.Y("price:Q", title="Median AED"),
                    color=alt.Color("platform_name:N", title="Platform"),
                    tooltip=["day:T", "platform_name:N", alt.Tooltip("price:Q", format=".2f")],
                ).properties(height=300), use_container_width=True,
            )


def _render_price_comparison(repo, competitors, platforms):
    all_rows = get_latest_comparison_prices(repo.db_path)
    all_history = get_comparison_history(repo.db_path)
    competitor = st.selectbox("Restaurant / competitor", competitors, index=next(
        (i for i, c in enumerate(competitors) if c["code"] == "pizza_hut"), 0),
        format_func=lambda c: c["name"], key="menu_compare_competitor")
    rows = [r for r in all_rows if r["competitor_id"] == competitor["id"]]
    history = [r for r in all_history if r["competitor_id"] == competitor["id"]]
    categories = sorted({r["category_name"] for r in rows})
    sizes = sorted({r["normalized_size"] for r in rows})
    platform_names = [p["name"] for p in platforms]
    f1, f2, f3, f4 = st.columns(4)
    with f1:
        category_filter = st.selectbox("Category", ["All categories"] + categories, key="menu_category_filter")
    with f2:
        size_filter = st.selectbox("Pizza / item size", ["All sizes"] + sizes, key="menu_size_filter")
    with f3:
        platform_filter = st.multiselect("Platforms", platform_names, default=platform_names, key="menu_platform_filter")
    with f4:
        availability_filter = st.selectbox("Availability", ["All", "Available", "Unavailable", "Unknown"], key="menu_availability_filter")
    f5, f6 = st.columns([2, 1])
    with f5:
        search = st.text_input("Search menu item", key="menu_comparison_search")
    with f6:
        min_gap = st.number_input("Minimum price gap (AED)", min_value=0.0, value=0.0, step=1.0, key="menu_min_gap")
    selected_platform_ids = {p["id"] for p in platforms if p["name"] in platform_filter}
    filtered = [r for r in rows if r["platform_id"] in selected_platform_ids]
    if category_filter != "All categories":
        filtered = [r for r in filtered if r["category_name"] == category_filter]
    if size_filter != "All sizes":
        filtered = [r for r in filtered if r["normalized_size"] == size_filter]
    if availability_filter != "All":
        filtered = [r for r in filtered if (r.get("availability") or "unknown") == availability_filter.casefold()]
    if search:
        filtered = [r for r in filtered if search.casefold() in (r["item_name"] + " " + (r.get("ingredients") or "")).casefold()]
    groups = _comparison_groups(filtered, platforms, history)
    if min_gap > 0:
        groups = [g for g in groups if g["Price gap (AED)"] is not None and g["Price gap (AED)"] >= min_gap]
    if groups:
        visible_columns = ["Brand", "Item", "Category", "Size", "Crust", "Emirate", "Location"]
        for name in platform_names:
            visible_columns.extend([f"{name} (AED)", f"{name} status"])
        visible_columns.extend(["Price gap (AED)", "Price gap (%)", "Cheapest recorded", "Most expensive recorded", "Last updated", "Source status", "Recent change"])
        df = pd.DataFrame(groups)[visible_columns]
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption("Rows compare the same canonical product variant and size. Missing prices stay blank; differing/unreviewed records retain their status.")
    else:
        st.info("No comparable observations match these filters. Import source-backed menu data and approve exact mappings to add more comparisons.")


def _render_import_and_mapping(repo, competitors, platforms, emirates):
    tab_import, tab_manual, tab_review = st.tabs(["CSV / Excel import", "Manual menu entry", "Match & price review"])
    with tab_import:
        st.download_button("Download blank import template", _make_csv_template(), "menu_import_template.csv", "text/csv")
        st.caption("Required per row: item name, category code, size, availability and source URL. A price is required for available items. Uploaded data is stored unverified until reviewed.")
        c1, c2, c3, c4 = st.columns(4)
        competitor = c1.selectbox("Brand", competitors, index=next((i for i,c in enumerate(competitors) if c["code"]=="pizza_hut"),0), format_func=lambda c:c["name"], key="menu_import_brand")
        platform = c2.selectbox("Menu platform", platforms, format_func=lambda p:p["name"], key="menu_import_platform")
        emirate = c3.selectbox("Emirate", emirates, index=next((i for i,e in enumerate(emirates) if e["code"]=="DXB"),0), format_func=lambda e:e["name_en"], key="menu_import_emirate")
        reviewer = c4.text_input("Imported by", key="menu_imported_by")
        file = st.file_uploader("Upload menu CSV or Excel (.csv / .xlsx)", type=["csv", "xlsx"], key="menu_import_file")
        if file:
            try:
                rows = parse_menu_upload(file.getvalue(), file.name)
                st.success(f"Validated {len(rows)} source-backed menu rows. No data has been saved yet.")
                st.dataframe(pd.DataFrame(rows).drop(columns=["source_item_key", "normalized_name"]), use_container_width=True, hide_index=True)
                if st.button("Import menu and append price history", type="primary", key="menu_import_submit"):
                    result = import_menu_csv(file.getvalue(), file.name, competitor["id"], platform["id"], emirate["id"], reviewer, repo.db_path)
                    st.success(f"Imported {result['items_imported']} menu entries. {result['match_suggestions']} suggestions await review; all prices start unverified.")
                    st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        batches = get_recent_menu_imports(repo.db_path)
        if batches:
            st.subheader("Recent import history")
            st.dataframe(pd.DataFrame(batches), use_container_width=True, hide_index=True)
            selected_batch = st.selectbox("Download original import file", batches, format_func=lambda b: f"{b['file_name']} — {b['imported_at']}", key="menu_download_batch")
            batch = get_menu_import_content(selected_batch["id"], repo.db_path)
            if batch and batch["sha256_valid"]:
                st.download_button("Download original uploaded file", batch["content"], batch["file_name"], key="download_original_import")
            else:
                st.error("The retained import file is missing or its hash does not match.")
    with tab_manual:
        st.caption("Manual records use the same source, audit, and review pipeline as file imports.")
        c1,c2,c3,c4=st.columns(4)
        comp=c1.selectbox("Brand",competitors,index=next((i for i,c in enumerate(competitors) if c["code"]=="pizza_hut"),0),format_func=lambda c:c["name"],key="manual_menu_brand")
        plat=c2.selectbox("Platform",platforms,format_func=lambda p:p["name"],key="manual_menu_platform")
        em=c3.selectbox("Emirate",emirates,index=next((i for i,e in enumerate(emirates) if e["code"]=="DXB"),0),format_func=lambda e:e["name_en"],key="manual_menu_emirate")
        reviewer= c4.text_input("Recorded by",key="manual_menu_reviewer")
        with st.form("manual_menu_item_form"):
            name=st.text_input("Exact item name on platform")
            cats=repo.get_all_categories()
            category=st.selectbox("Category",cats,format_func=lambda x:x["name"])
            size=st.selectbox("Size",["Personal","Small","Medium","Large","X-Large","Other"])
            crust=st.text_input("Crust / variation shown by source")
            ingredients=st.text_area("Ingredients as shown (optional)")
            availability=st.selectbox("Availability","Available Unavailable Unknown".split())
            price=st.text_input("Observed item price in AED (blank only if unavailable/unknown)")
            source=st.text_input("Source URL (required)")
            submitted=st.form_submit_button("Record menu item and price")
            if submitted:
                try:
                    output=io.StringIO()
                    writer=csv.writer(output)
                    writer.writerow(["item_name","category","size_name","price","availability","crust_type","ingredients","source_url"])
                    writer.writerow([name,category["code"],size,price,availability.casefold(),crust,ingredients,source])
                    result=import_menu_csv(output.getvalue().encode(),"manual-menu-entry.csv",comp["id"],plat["id"],em["id"],reviewer,repo.db_path)
                    st.success(f"Menu price recorded in run #{result['research_run_id']} as unverified.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    with tab_review:
        st.subheader("External menu items awaiting a canonical mapping")
        unmatched=get_unmatched_menu_items(db_path=repo.db_path)
        if unmatched:
            st.dataframe(pd.DataFrame(unmatched)[["item_name","platform_name","category_name","size_name","crust_type","price","verification_status","source_url"]],use_container_width=True,hide_index=True)
            item=st.selectbox("Menu item to review",unmatched,format_func=lambda x:f"{x['item_name']} — {x['platform_name']} — {x['size_name']}",key="menu_match_item")
            suggestions=__import__("src.menu_mapping.service",fromlist=["get_match_suggestions"]).get_match_suggestions(item["id"],repo.db_path)
            candidates=[v for v in get_canonical_variants(item["competitor_id"],repo.db_path) if v["category_id"]==item["category_id"] and v["normalized_size"]==item["normalized_size"]]
            if not candidates:
                st.info("No canonical product variant with the same category and size exists yet. Add it in Catalog & Branch Manager first.")
            else:
                suggested_ids={s["product_variant_id"] for s in suggestions}
                candidates.sort(key=lambda x:(x["product_variant_id"] not in suggested_ids,x["item_name"]))
                target=st.selectbox("Candidate canonical item (same category and size only)",candidates,format_func=lambda x:f"{x['item_name']} — {x['size_name']} — {x['crust_type']}",key="menu_match_target")
                confidence=next((s["confidence_score"] for s in suggestions if s["product_variant_id"]==target["product_variant_id"]),None)
                if confidence is not None:
                    st.caption(f"Suggested ranking score: {confidence:.2f}. This is not a probability and does not approve the match.")
                st.write("Candidate ingredients:",target.get("ingredients") or "Not recorded")
                reviewer=st.text_input("Match reviewer",key="menu_match_reviewer")
                confirm=st.checkbox("I checked the source, crust, ingredients and variation; approve this exact-size mapping",key="menu_match_confirm")
                if st.button("Approve selected mapping",type="primary",key="approve_menu_mapping"):
                    try:
                        approve_menu_match(item["id"],target["product_variant_id"],reviewer,confirm,repo.db_path)
                        st.success("Mapping approved. Only then will these source prices enter the mapped comparison.")
                        st.rerun()
                    except ValueError as exc:
                        st.error(str(exc))
                rejected=[s for s in suggestions if s["status"]=="suggested"]
                if rejected:
                    selected_reject=st.selectbox("Reject a suggested candidate",rejected,format_func=lambda s:f"{s['product_name']} — score {s['confidence_score']:.2f}",key="reject_menu_candidate")
                    if st.button("Reject selected suggestion",key="reject_menu_suggestion"):
                        reject_menu_match(selected_reject["match_id"],reviewer,repo.db_path)
                        st.success("Suggestion rejected and retained in the audit trail.")
                        st.rerun()
        else:
            st.info("No imported platform items are waiting for a mapping.")

        st.subheader("Imported prices awaiting human verification")
        unverified=get_unverified_menu_prices(repo.db_path)
        if unverified:
            price_row=st.selectbox("Imported price",unverified,format_func=lambda x:f"{x['item_name']} / {x['size_name']} — {x['platform_name']} — {x['price'] if x['price'] is not None else 'price unavailable'} AED",key="verify_menu_price_row")
            st.link_button("Open recorded source",price_row["source_url"])
            st.caption("Verification requires checking the actual source page against the retained import file; mapping approval alone does not verify a price.")
            reviewer=st.text_input("Price reviewer",key="verify_menu_price_reviewer")
            confirmed=st.checkbox("I confirmed this exact price, size and availability at the source",key="verify_menu_price_confirm")
            if st.button("Verify selected imported price",disabled=not confirmed,key="verify_menu_price"):
                verify_menu_price(price_row["price_id"],reviewer,repo.db_path)
                st.success("Price verification recorded.")
                st.rerun()
        else:
            st.info("No imported menu price is awaiting review.")

        approved=get_approved_menu_matches(repo.db_path)
        if approved:
            st.subheader("Approved mappings — reject to reopen a correction")
            st.dataframe(pd.DataFrame(approved),use_container_width=True,hide_index=True)
            old=st.selectbox("Mapping to reopen",approved,format_func=lambda x:f"{x['item_name']} ({x['platform_name']}) → {x['canonical_name']} / {x['canonical_size']}",key="reopen_menu_match")
            who=st.text_input("Reviewer for correction",key="reopen_menu_reviewer")
            if st.button("Reject mapping and reopen for review",key="reopen_menu_mapping"):
                reject_menu_match(old["match_id"],who,repo.db_path)
                st.success("Mapping rejected; historical price rows remain preserved.")
                st.rerun()


def _render_fees_and_cart(repo, competitors, platforms, emirates):
    fee_tab, cart_tab=st.tabs(["Delivery / checkout charges","Cart comparison"])
    with fee_tab:
        fees=get_latest_fee_observations(repo.db_path)
        st.subheader("Latest recorded charges by platform and location")
        if fees:
            df=pd.DataFrame(fees)
            st.dataframe(df[["competitor_name","platform_name","emirate_name","location_name","delivery_fee","service_fee","small_order_fee","packaging_fee","other_fee","minimum_order_amount","observed_at","verification_status"]],use_container_width=True,hide_index=True)
        else:
            st.info("No delivery or checkout-fee observations are recorded. Blank values remain unknown; do not treat them as zero.")
        st.divider()
        st.subheader("Record fees from a real checkout or source page")
        c1,c2,c3,c4=st.columns(4)
        comp=c1.selectbox("Brand",competitors,index=next((i for i,c in enumerate(competitors) if c["code"]=="pizza_hut"),0),format_func=lambda c:c["name"],key="fee_brand")
        plat=c2.selectbox("Platform",platforms,format_func=lambda p:p["name"],key="fee_platform")
        em=c3.selectbox("Emirate",emirates,index=next((i for i,e in enumerate(emirates) if e["code"]=="DXB"),0),format_func=lambda e:e["name_en"],key="fee_emirate")
        reviewer=c4.text_input("Collected by",key="fee_reviewer")
        locations=repo.get_locations(comp["id"],em["id"])
        location_opts=[{"id":None,"branch_name":"Location not recorded"}]+locations
        location=st.selectbox("Delivery location",location_opts,format_func=lambda x:x["branch_name"],key="fee_location")
        with st.form("fee_observation_form"):
            fee_cols=st.columns(3)
            fields=[("Delivery fee","delivery_fee"),("Service fee","service_fee"),("Small-order fee","small_order_fee"),("Packaging fee","packaging_fee"),("Other checkout fee","other_fee"),("Minimum order","minimum_order_amount")]
            fees_input={}
            for i,(label,key) in enumerate(fields):
                with fee_cols[i%3]:
                    fees_input[key]=_optional_amount(f"{label} (AED; blank means unknown)",f"fee_{key}")
            source=st.text_input("Checkout/source URL",key="fee_source_url")
            evidence,evidence_name=_evidence_upload("Checkout screenshot or HTML capture (required to mark fees verified)","fee_evidence")
            submit=st.form_submit_button("Save charge observation")
            if submit:
                try:
                    fee_id=save_fee_observation(comp["id"],plat["id"],em["id"],source,fees_input,reviewer,evidence,evidence_name,location["id"],repo.db_path)
                    st.success(f"Fee observation #{fee_id} saved; status: {'verified' if evidence else 'unverified'}.")
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))

    with cart_tab:
        st.caption("A total is shown only when every selected item, availability and required charge is known. Otherwise only known subtotals are shown.")
        comp=st.selectbox("Restaurant",competitors,index=next((i for i,c in enumerate(competitors) if c["code"]=="pizza_hut"),0),format_func=lambda c:c["name"],key="cart_brand")
        em=st.selectbox("Delivery emirate",emirates,index=next((i for i,e in enumerate(emirates) if e["code"]=="DXB"),0),format_func=lambda e:e["name_en"],key="cart_emirate")
        locations=repo.get_locations(comp["id"],em["id"])
        location_opts=[{"id":None,"branch_name":"No specific location"}]+locations
        location=st.selectbox("Delivery location",location_opts,format_func=lambda x:x["branch_name"],key="cart_location")
        variants=get_canonical_variants(comp["id"],repo.db_path)
        chosen=st.multiselect("Items / exact sizes",variants,format_func=lambda x:f"{x['item_name']} — {x['size_name']} — {x['crust_type']}",key="cart_items")
        quantities={}
        customizations={}
        if chosen:
            st.write("Quantities")
            qcols=st.columns(min(4,len(chosen)))
            for i,item in enumerate(chosen):
                with qcols[i%len(qcols)]:
                    quantities[item["product_variant_id"]]=st.number_input(
                        f"{item['item_name']} / {item['size_name']}",min_value=1,max_value=50,value=1,step=1,key=f"cart_qty_{item['product_variant_id']}"
                    )
                    customizations[item["product_variant_id"]]={
                        "amount": st.number_input("Customization charge per item (AED)",min_value=0.0,value=0.0,step=0.5,key=f"cart_custom_charge_{item['product_variant_id']}"),
                        "notes": st.text_input("Customization notes",key=f"cart_custom_note_{item['product_variant_id']}"),
                    }
        if quantities:
            comparison=get_latest_comparison_prices(repo.db_path)
            offers=get_promotion_records(repo.db_path)
            quotes=calculate_cart_quotes(comp["id"],em["id"],quantities,comparison,get_latest_fee_observations(repo.db_path),offers,location["id"],platforms,customizations)
            cards=st.columns(min(4,max(1,len(quotes))))
            for i,quote in enumerate(quotes):
                with cards[i%len(cards)]:
                    st.markdown(f"**{quote['platform_name']}**")
                    st.caption("Estimate" if quote["quote_status"]=="estimate" else "Incomplete")
                    st.metric("Item subtotal",f"AED {quote['item_subtotal']:.2f}" if quote["item_subtotal"] is not None else "Unavailable")
                    st.metric("Customizations",f"AED {quote['customization_total']:.2f}")
                    st.metric("Estimated total",f"AED {quote['final_total']:.2f}" if quote["final_total"] is not None else "Unknown")
                    st.caption(quote["notes"])
                    if quote.get("promotion_title"):
                        st.caption(f"Applied computable verified offer: {quote['promotion_title']} (single offer; stacking not assumed).")
                    breakdown={k.replace("_"," ").title():v for k,v in quote.items() if k in {"delivery_fee","service_fee","small_order_fee","packaging_fee","other_fee"}}
                    st.write({k:(f"AED {v:.2f}" if v is not None else "Unknown") for k,v in breakdown.items()})
            complete=[q for q in quotes if q["final_total"] is not None]
            if complete:
                best=min(complete,key=lambda q:q["final_total"])
                st.info(f"Lowest complete estimate: {best['platform_name']} — AED {best['final_total']:.2f}. This is not a verified checkout total.")
            else:
                st.info("No platform currently has enough verified item, availability and fee data to calculate a complete total.")
            created_by=st.text_input("Cart comparison recorded by",key="cart_created_by")
            if st.button("Save this cart comparison",key="save_cart_comparison"):
                comparison_id=save_cart_comparison(comp["id"],em["id"],quantities,quotes,created_by,repo.db_path,location["id"],customizations)
                st.success(f"Cart comparison #{comparison_id} saved with each platform's estimate/incomplete status.")
                st.rerun()
        else:
            st.info("Select one or more canonical menu variants to compare a cart.")


def _render_promotions(repo, competitors, platforms, emirates):
    offers=get_promotion_records(repo.db_path)
    c1,c2=st.columns(2)
    platform_filter=c1.selectbox("Filter promotion platform",["All platforms"]+platforms,format_func=lambda p:p if isinstance(p,str) else p["name"],key="promo_platform_filter")
    status_filter=c2.selectbox("Filter status",["All statuses","Active","Upcoming","Expired","Stale","Unverified","Needs review"],key="promo_status_filter")
    if not isinstance(platform_filter,str):
        offers=[p for p in offers if p.get("platform_id")==platform_filter["id"]]
    if status_filter!="All statuses":
        offers=[p for p in offers if promotion_status(p)==status_filter]
    if offers:
        visible=[]
        for p in offers:
            visible.append({"Promotion":p["title"],"Brand":p["competitor_name"],"Platform":p.get("platform_name") or "Not specified",
                            "Type":_PROMOTION_LABELS.get(p.get("promotion_type") or p["promo_type"],p["promo_type"]),
                            "Discount":p.get("discount_percentage") and f"{p['discount_percentage']}%" or (f"AED {p['discount_amount']}" if p.get("discount_amount") is not None else "Terms-based"),
                            "Minimum order":p.get("minimum_order_value"),"Maximum discount":p.get("maximum_discount"),
                            "Start":p.get("starts_at"),"End":p.get("ends_at"),"Days":", ".join(_DAYS[d] for d in p["weekdays"]),
                            "Last verified":p.get("last_verified_at"),"Status":promotion_status(p),"Source":p["source_url"]})
        st.dataframe(pd.DataFrame(visible),use_container_width=True,hide_index=True)
    else:
        st.info("No promotion matches this filter.")
    st.subheader("Promotion calendar")
    mode=st.selectbox("Calendar range",["Day","Week","Month"],key="promo_calendar_mode")
    selected=st.date_input("Calendar date",value=date.today(),key="promo_calendar_date")
    if mode=="Day":
        start=end=selected
    elif mode=="Week":
        start=selected-timedelta(days=selected.weekday()); end=start+timedelta(days=6)
    else:
        start=date(selected.year,selected.month,1); end=date(selected.year,selected.month,calendar.monthrange(selected.year,selected.month)[1])
    events=[]
    current=start
    while current<=end:
        for promo in offers:
            if promotion_status(promo,current) not in {"Active","Upcoming"} or current.weekday() not in promo["weekdays"]:
                continue
            events.append({"Date":current.isoformat(),"Day":_DAYS[current.weekday()],"Promotion":promo["title"],"Platform":promo.get("platform_name") or "Not specified","Status":promotion_status(promo,current)})
        current+=timedelta(days=1)
    if events:
        st.dataframe(pd.DataFrame(events),use_container_width=True,hide_index=True)
    else:
        st.info("No verified promotions are scheduled in this range. Existing legacy offers without source verification and weekday data are not put on the calendar.")

    st.divider()
    st.subheader("Record or verify a promotion")
    c1,c2,c3,c4=st.columns(4)
    comp=c1.selectbox("Brand",competitors,index=next((i for i,c in enumerate(competitors) if c["code"]=="pizza_hut"),0),format_func=lambda c:c["name"],key="promo_brand")
    plat_options=[{"id":None,"name":"Not platform-specific"}]+platforms
    plat=c2.selectbox("Platform",plat_options,format_func=lambda p:p["name"],key="promo_entry_platform")
    em_options=[{"id":None,"name_en":"Any / unspecified"}]+emirates
    em=c3.selectbox("Emirate",em_options,format_func=lambda e:e["name_en"],key="promo_entry_emirate")
    reviewer=c4.text_input("Verified / recorded by",key="promo_reviewer")
    with st.form("menu_promotion_form"):
        title=st.text_input("Promotion name")
        ptype=st.selectbox("Promotion type",PROMOTION_TYPES,format_func=lambda x:_PROMOTION_LABELS[x])
        promo_code=st.text_input("Promo code (optional)")
        description=st.text_area("Eligibility, terms and conditions (include limits as stated)")
        date_cols=st.columns(2)
        has_start=date_cols[0].checkbox("Has start date",key="promo_has_start")
        start=date_cols[0].date_input("Start date",value=date.today(),key="promo_start") if has_start else None
        has_end=date_cols[1].checkbox("Has end date",key="promo_has_end")
        end=date_cols[1].date_input("End date",value=date.today(),key="promo_end") if has_end else None
        weekdays=st.multiselect("Applicable weekdays (only select when the source states them)",list(range(7)),format_func=lambda d:_DAYS[d],key="promo_weekdays")
        eligibility=get_canonical_variants(comp["id"],repo.db_path)
        eligible=st.multiselect("Eligible exact menu variants (leave empty when source gives no item-level eligibility)",eligibility,format_func=lambda x:f"{x['item_name']} — {x['size_name']} — {x['crust_type']}",key="promo_eligible_variants")
        val_cols=st.columns(3)
        discount_amount=_optional_amount("Fixed discount AED (blank if not stated)","promo_discount_amount")
        discount_percentage=_optional_amount("Discount percentage (blank if not stated)","promo_discount_percent")
        minimum=_optional_amount("Minimum order AED (blank if unknown)","promo_minimum_order")
        maximum=_optional_amount("Maximum discount AED (blank if unknown)","promo_maximum_discount")
        evidence,evidence_name=_evidence_upload("Source screenshot / HTML (needed for verified status)","promo_evidence")
        source=st.text_input("Public source URL")
        submit=st.form_submit_button("Save promotion and schedule")
        if submit:
            try:
                pid=save_promotion(comp["id"],plat["id"],em["id"],title,description,ptype,source,
                    discount_amount,discount_percentage,start.isoformat() if start else None,end.isoformat() if end else None,
                    minimum,maximum,weekdays,reviewer,evidence,evidence_name,[x["product_variant_id"] for x in eligible],repo.db_path,
                    promo_code=promo_code)
                st.success(f"Promotion #{pid} saved; status is {'verified' if evidence else 'unverified'}.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def render_menu_analysis_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Menu Mapping & Competitor Analysis",
        subtitle="Source-backed menu alignment, cross-platform price gaps, checkout fees, promotions and cart estimates",
    )
    competitors=repo.get_all_competitors()
    platforms=repo.get_all_platforms()
    emirates=repo.get_all_emirates()
    if not competitors or not platforms or not emirates:
        st.error("Competitor, platform, or emirate reference data is unavailable.")
        return
    default_id=_default_competitor(competitors)
    default_comp=next(c for c in competitors if c["id"]==default_id)
    st.caption(f"Restaurant selected for the dashboard: {default_comp['name']}. Other tracked brands can be selected in comparison views.")
    dashboard_comp=st.selectbox("Dashboard brand",competitors,index=next(i for i,c in enumerate(competitors) if c["id"]==default_id),format_func=lambda c:c["name"],key="menu_dashboard_brand")
    tab_dashboard,tab_prices,tab_mapping,tab_fees,tab_promos,tab_sources=st.tabs([
        "Dashboard","Price comparison","Menu import & mapping","Fees & cart","Promotions calendar","Data sources"
    ])
    with tab_dashboard:
        _render_dashboard(repo,competitors,platforms,dashboard_comp["id"])
    with tab_prices:
        _render_price_comparison(repo,competitors,platforms)
    with tab_mapping:
        _render_import_and_mapping(repo,competitors,platforms,emirates)
    with tab_fees:
        _render_fees_and_cart(repo,competitors,platforms,emirates)
    with tab_promos:
        _render_promotions(repo,competitors,platforms,emirates)
    with tab_sources:
        st.subheader("Permitted data access and integration status")
        st.caption("Automated platform integrations are not called unless approved partner credentials and access are supplied. No authentication, CAPTCHA, or access control is bypassed.")
        for platform in platforms:
            access=integration_for(platform["code"])
            st.markdown(f"**{platform['name']}** — {access['method']}")
            st.write(access["status"])
            if access.get("url"):
                st.link_button(f"Official {platform['name']} partner documentation",access["url"])
        st.info("CSV/XLSX uploads and audited manual entry are available for platforms without an approved feed. Add another platform in the existing platform catalog; no prices are assumed for an unmonitored platform.")

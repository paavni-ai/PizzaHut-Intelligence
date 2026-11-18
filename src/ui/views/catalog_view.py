"""
Competitors, UAE Branches & Product Catalog Management View.
"""
import pandas as pd
import streamlit as st

from src.db.repository import PizzaIntelligenceRepository
from src.ui.styles import render_brand_header


def render_catalog_view(repo: PizzaIntelligenceRepository):
    render_brand_header(
        page_title="Catalog & Branch Manager",
        subtitle="Manage competitor profiles, physical branch networks across 7 emirates, and product sizes",
    )

    tab1, tab2, tab3 = st.tabs([
        "🏢 Competitor Brands",
        "📍 UAE Store Branches",
        "🍕 Products & Size Variants",
    ])

    # -------------------------------------------------------------------------
    # TAB 1: Competitors Management
    # -------------------------------------------------------------------------
    with tab1:
        st.subheader("Tracked Competitor Brands")
        competitors = repo.get_all_competitors(include_inactive=True)
        df_comp = pd.DataFrame(competitors)[["id", "code", "name", "website_url", "is_active", "notes"]]
        df_comp.columns = ["ID", "Code", "Brand Name", "Official Website", "Active", "Notes"]
        st.dataframe(df_comp, use_container_width=True)

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("➕ Add New Competitor Brand"):
            with st.form("add_competitor_form"):
                ac_code = st.text_input("Brand Code (lowercase, e.g. yellow_cab)", placeholder="e.g. yellow_cab")
                ac_name = st.text_input("Brand Name", placeholder="e.g. Yellow Cab Pizza")
                ac_url = st.text_input("Official Website URL", placeholder="https://www.yellowcabpizza.ae")
                ac_notes = st.text_area("Notes", placeholder="Local UAE pizza competitor")
                ac_submit = st.form_submit_button("Add Competitor", type="primary")

                if ac_submit:
                    if not ac_code.strip() or not ac_name.strip():
                        st.error("Code and Name are required.")
                    else:
                        try:
                            cid = repo.add_competitor(ac_code.strip().lower(), ac_name.strip(), ac_url.strip(), ac_notes.strip())
                            st.success(f"Competitor '{ac_name}' added successfully (ID #{cid}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding competitor: {e}")

    # -------------------------------------------------------------------------
    # TAB 2: UAE Branches Directory & Management
    # -------------------------------------------------------------------------
    with tab2:
        st.subheader("Physical Store Locations Across 7 Emirates")
        locations = repo.get_locations()
        if locations:
            df_loc = pd.DataFrame(locations)[[
                "id", "competitor_name", "emirate_name", "branch_name", "area", "address", "phone"
            ]]
            df_loc.columns = ["Branch ID", "Brand", "Emirate", "Branch Name", "Area", "Address", "Phone"]
            st.dataframe(df_loc, use_container_width=True, height=350)
        else:
            st.info("No branches recorded yet.")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("📍 Add New UAE Branch Location"):
            comps = repo.get_all_competitors()
            ems = repo.get_all_emirates()
            with st.form("add_branch_form"):
                b_col1, b_col2 = st.columns(2)
                with b_col1:
                    b_comp = st.selectbox("Select Brand", options=comps, format_func=lambda c: c["name"])
                    b_em = st.selectbox("Select Emirate", options=ems, format_func=lambda e: f"{e['name_en']} ({e['code']})")
                    b_name = st.text_input("Branch Name", placeholder="e.g. Al Majaz Waterfront")
                with b_col2:
                    b_area = st.text_input("Area / District", placeholder="e.g. Al Majaz 2")
                    b_addr = st.text_input("Street Address", placeholder="e.g. Corniche Road, Sharjah")
                    b_phone = st.text_input("Contact Phone", placeholder="e.g. +971 600 569999")

                b_submit = st.form_submit_button("Add Branch Location", type="primary")
                if b_submit:
                    if not b_name.strip():
                        st.error("Branch name is required.")
                    else:
                        try:
                            lid = repo.add_location(
                                competitor_id=b_comp["id"],
                                emirate_id=b_em["id"],
                                branch_name=b_name.strip(),
                                area=b_area.strip(),
                                address=b_addr.strip(),
                                phone=b_phone.strip(),
                            )
                            st.success(f"Branch '{b_name}' added successfully (ID #{lid}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error adding branch: {e}")

    # -------------------------------------------------------------------------
    # TAB 3: Products & Size Variants
    # -------------------------------------------------------------------------
    with tab3:
        st.subheader("Menu Items & Size Variants Catalog")
        products = repo.get_products_with_variants()
        if products:
            df_prod = pd.DataFrame(products)[[
                "product_id", "competitor_name", "category_name", "product_name",
                "size_name", "normalized_size", "crust_type", "ingredients", "diameter_inches"
            ]]
            df_prod.columns = [
                "Product ID", "Brand", "Category", "Item Name",
                "Size Name", "Normalized Size", "Crust Type", "Ingredients / defining toppings", "Diameter (Inches)"
            ]
            st.dataframe(df_prod, use_container_width=True, height=350)
        else:
            st.info("No products configured yet.")

        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("🍕 Add New Product & Variant"):
            comps = repo.get_all_competitors()
            cats = repo.get_all_categories()
            with st.form("add_product_form"):
                p_c1, p_c2 = st.columns(2)
                with p_c1:
                    p_comp = st.selectbox("Select Brand", options=comps, format_func=lambda c: c["name"], key="p_comp_sel")
                    p_cat = st.selectbox("Select Category", options=cats, format_func=lambda c: c["name"])
                    p_name = st.text_input("Product Name", placeholder="e.g. Chicken Fajita")
                    p_norm = st.text_input("Canonical Name (e.g. chicken_fajita)", placeholder="chicken_fajita")
                    p_ingredients = st.text_area("Ingredients / defining toppings (optional)")
                with p_c2:
                    p_size = st.selectbox("Size Label", options=["Small", "Medium", "Large", "Personal", "X-Large"])
                    p_norm_size = st.selectbox("Normalized Size", options=["small", "medium", "large", "personal", "xlarge", "other"])
                    p_crust = st.text_input("Crust Type", value="Standard")
                    p_diam = st.number_input("Diameter in Inches (Optional)", value=10.0, step=0.5)

                p_submit = st.form_submit_button("Create Product & Size", type="primary")
                if p_submit:
                    if not p_name.strip():
                        st.error("Product name is required.")
                    else:
                        try:
                            new_pid = repo.get_or_create_product(
                                competitor_id=p_comp["id"],
                                category_id=p_cat["id"],
                                name=p_name.strip(),
                                normalized_name=p_norm.strip() or p_name.strip().lower().replace(" ", "_"),
                                ingredients=p_ingredients.strip() or None,
                            )
                            new_vid = repo.get_or_create_variant(
                                product_id=new_pid,
                                size_name=p_size,
                                normalized_size=p_norm_size,
                                crust_type=p_crust.strip(),
                                diameter_inches=p_diam,
                            )
                            st.success(f"Product '{p_name}' ({p_size}) created successfully (Product #{new_pid}, Variant #{new_vid}).")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error creating product: {e}")

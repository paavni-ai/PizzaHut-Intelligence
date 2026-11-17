"""
Commercial SaaS Theme and CSS Styling for UAE Pizza Price Intelligence.
"""
import streamlit as st


def apply_custom_styles():
    st.markdown(
        """
        <style>
        /* Base typography & fonts */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Top Brand Header */
        .brand-header {
            background: linear-gradient(135deg, #0A192F 0%, #1E293B 100%);
            padding: 18px 24px;
            border-radius: 12px;
            color: #ffffff;
            margin-bottom: 24px;
            border-left: 6px solid #C8102E;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
        }
        .brand-header h1 {
            font-size: 1.6rem;
            font-weight: 800;
            margin: 0;
            color: #ffffff !important;
            letter-spacing: -0.02em;
        }
        .brand-header p {
            font-size: 0.9rem;
            color: #94A3B8;
            margin: 4px 0 0 0;
        }

        /* Metric KPI Card */
        .kpi-container {
            background: #ffffff;
            border: 1px solid #E2E8F0;
            border-radius: 10px;
            padding: 16px 20px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
            margin-bottom: 16px;
            transition: all 0.2s ease;
        }
        .kpi-container:hover {
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
            border-color: #CBD5E1;
        }
        .kpi-title {
            font-size: 0.8rem;
            text-transform: uppercase;
            font-weight: 700;
            color: #64748B;
            letter-spacing: 0.05em;
            margin-bottom: 6px;
        }
        .kpi-value {
            font-size: 1.8rem;
            font-weight: 800;
            color: #0F172A;
            line-height: 1.1;
        }
        .kpi-sub {
            font-size: 0.8rem;
            color: #64748B;
            margin-top: 6px;
        }

        /* Status Badges */
        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 6px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }
        .badge-verified {
            background-color: #ECFDF5;
            color: #065F46;
            border: 1px solid #A7F3D0;
        }
        .badge-review {
            background-color: #FFFBEB;
            color: #92400E;
            border: 1px solid #FDE68A;
        }
        .badge-unverified {
            background-color: #F1F5F9;
            color: #475569;
            border: 1px solid #CBD5E1;
        }
        .badge-unavailable {
            background-color: #FEF2F2;
            color: #991B1B;
            border: 1px solid #FECACA;
        }

        /* Section Container */
        .section-card {
            background: #ffffff;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 22px;
            margin-bottom: 24px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        }
        .section-title {
            font-size: 1.2rem;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 4px;
        }
        .section-desc {
            font-size: 0.85rem;
            color: #64748B;
            margin-bottom: 16px;
        }

        /* Price gap highlights */
        .gap-cheaper {
            color: #059669;
            font-weight: 700;
        }
        .gap-expensive {
            color: #DC2626;
            font-weight: 700;
        }
        .gap-equal {
            color: #475569;
            font-weight: 600;
        }

        /* Sidebar Styling */
        section[data-testid="stSidebar"] {
            background-color: #F8FAFC;
            border-right: 1px solid #E2E8F0;
        }

        /* Button Enhancements */
        div.stButton > button:first-child {
            font-weight: 600;
            border-radius: 8px;
            transition: all 0.15s ease;
        }
        div.stButton > button[kind="primary"] {
            background-color: #C8102E;
            border-color: #C8102E;
            color: white;
        }
        div.stButton > button[kind="primary"]:hover {
            background-color: #A00D24;
            border-color: #A00D24;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand_header(page_title: str, subtitle: str):
    st.markdown(
        f"""
        <div class="brand-header">
            <h1>🍕 UAE Pizza Price Intelligence — {page_title}</h1>
            <p>{subtitle} • All 7 Emirates • 4 Channels • 100% Genuine Evidence</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

import streamlit as st

st.set_page_config(
    page_title="UAE Pizza Price Intelligence",
    page_icon="🍕",
    layout="wide"
)

st.title("🍕 UAE Pizza Price Intelligence")
st.caption("Competitor pricing research and market intelligence")

st.info(
    "This is the initial prototype. No competitor prices have "
    "been collected yet. All future findings must be supported "
    "by genuine source evidence."
)

st.subheader("Research workspace")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Competitors tracked", "0")

with col2:
    st.metric("Products verified", "0")

with col3:
    st.metric("Price records collected", "0")

st.divider()

st.subheader("Research principles")

st.markdown("""
- Only use genuine, publicly accessible source information.
- Record the original source URL and collection timestamp.
- Record location and ordering method.
- Mark uncertain findings as **Needs review**.
- Never invent missing prices, products or promotions.
""")

st.subheader("Coming next")
st.write(
    "Competitor selection, product matching, price comparisons, "
    "historical tracking and Excel exports."
)

import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Garden For All | Live Heatmap",
    page_icon="🌱",
    layout="wide",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }
    h1, h2, h3 {
        font-family: 'DM Serif Display', serif !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'DM Serif Display', serif;
        font-size: 2.2rem !important;
        color: #2d6a4f;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.75rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #888;
    }
    section[data-testid="stSidebar"] {
        background-color: #f0f4f0;
    }
</style>
""", unsafe_allow_html=True)


# ── Data fetching ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=600)
def get_live_data():
    """
    Fetch pantry locations and food shipment data from Supabase.

    Schema assumptions:
      Pantry        → pantry_name (PK), location (PostGIS point as WKB hex)
      Food Shipments → pantry_name (FK → Pantry.pantry_name), weight (numeric)
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # ── Fetch raw tables ───────────────────────────────────────────────────────
    pantry_df    = pd.DataFrame(supabase.table("Pantry").select("*").execute().data)
    shipment_df  = pd.DataFrame(supabase.table("Food Shipments").select("*").execute().data)

    # ── Parse PostGIS WKB hex → (latitude, longitude) ─────────────────────────
    def wkb_to_latlon(hex_val):
        """Return (lat, lon) from a PostGIS WKB hex string, or (None, None)."""
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x   # PostGIS stores (lon, lat) → flip
        except Exception:
            return None, None

    pantry_df[["latitude", "longitude"]] = (
        pantry_df["location"]
        .apply(lambda x: pd.Series(wkb_to_latlon(x)))
    )

    # Drop pantries with no parseable location
    pantry_df = pantry_df.dropna(subset=["latitude", "longitude"])

    # ── Coerce shipment weights to numeric ─────────────────────────────────────
    shipment_df["weight"] = (
        pd.to_numeric(shipment_df["weight"], errors="coerce").fillna(0)
    )

    # ── Aggregate total weight delivered per pantry ────────────────────────────
    # pantry_name in Food Shipments is a FK to Pantry.pantry_name, so we can
    # group directly — no index-based mapping needed.
    pantry_weights = (
        shipment_df
        .groupby("pantry_name", as_index=False)["weight"]
        .sum()
        .rename(columns={"weight": "total_weight_lbs"})
    )

    # ── Join weights onto pantry coordinates ───────────────────────────────────
    # Left join so pantries with zero deliveries still appear on the map.
    final_df = pantry_df.merge(pantry_weights, on="pantry_name", how="left")
    final_df["total_weight_lbs"] = final_df["total_weight_lbs"].fillna(0)

    # ── Totals ─────────────────────────────────────────────────────────────────
    total_lbs    = shipment_df["weight"].sum()
    total_stops  = (pantry_weights["total_weight_lbs"] > 0).sum()

    return final_df, total_lbs, total_stops, pantry_weights


# ── Load data ──────────────────────────────────────────────────────────────────
try:
    map_data, total_lbs, total_stops, summary_df = get_live_data()
except Exception as e:
    st.error(f"❌ Could not load data from Supabase: {e}")
    st.info("Make sure SUPABASE_URL and SUPABASE_KEY are set in your Streamlit secrets.")
    st.stop()


# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🌱 Garden For All")
    st.divider()

    col1, col2 = st.columns(2)
    col1.metric("Total Impact", f"{total_lbs:,.1f} lbs")
    col2.metric("Active Pantries", int(total_stops))

    st.divider()
    st.markdown("### Delivery Summary")

    display_df = (
        summary_df
        .rename(columns={"pantry_name": "Pantry", "total_weight_lbs": "lbs Delivered"})
        .sort_values("lbs Delivered", ascending=False)
        .reset_index(drop=True)
    )
    display_df["lbs Delivered"] = display_df["lbs Delivered"].map("{:,.1f}".format)

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.divider()
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()


# ── Main page ──────────────────────────────────────────────────────────────────
st.title("Garden For All — Live Distribution Heatmap")
st.caption("Real-time food shipment data across Columbus, Ohio")


# ── Map generation ─────────────────────────────────────────────────────────────
def generate_map(df: pd.DataFrame) -> folium.Map:
    """Build a Folium map with a heatmap layer and pantry markers."""
    m = folium.Map(
        location=[39.9612, -82.9988],   # Columbus, OH
        zoom_start=11,
        tiles="cartodbpositron",
    )

    # Heatmap — only include pantries that actually received deliveries
    heat_rows = df[df["total_weight_lbs"] > 0]
    heat_data = heat_rows[["latitude", "longitude", "total_weight_lbs"]].values.tolist()

    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # One marker per pantry (including those with zero deliveries)
    for _, row in df.iterrows():
        weight    = row["total_weight_lbs"]
        icon_color = "darkblue" if weight > 0 else "gray"
        tooltip   = (
            f"<b>{row['pantry_name']}</b><br>"
            f"{weight:,.1f} lbs delivered"
        )
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            icon=folium.Icon(color=icon_color, icon="shopping-cart", prefix="fa"),
            tooltip=folium.Tooltip(tooltip, sticky=True),
        ).add_to(m)

    return m


st_folium(
    generate_map(map_data),
    width="100%",
    height=600,
    returned_objects=[],   # prevents unnecessary reruns on map interaction
)

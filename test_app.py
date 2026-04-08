import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Fetch Pantry Table (The Source of Truth for names/coords)
    pantry_res = supabase.table("Pantry").select("*").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. Fetch Shipments Table
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # 3. Clean and Standardize Pantry Coordinates
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 4. THE FIX: Standardize all names to strings immediately
    # This prevents the 'None' or 'Unknown' issue caused by foreign key IDs
    pantry_df['pantry_name'] = pantry_df['pantry_name'].astype(str).str.strip()
    shipment_df['pantry_name'] = shipment_df['pantry_name'].astype(str).str.strip()

    # 5. Math
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    total_lbs = shipment_df['weight'].sum()

    # Create matching keys
    pantry_df['match_key'] = pantry_df['pantry_name'].str.lower()
    shipment_df['match_key'] = shipment_df['pantry_name'].str.lower()

    # 6. Aggregate and Merge
    pantry_weights = shipment_df.groupby('match_key')['weight'].sum().reset_index()
    final_df = pd.merge(pantry_df, pantry_weights, on="match_key", how="left")
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, total_lbs, shipment_df

# --- EXECUTION ---
try:
    map_data, total_impact_lbs, debug_df = get_live_data()

    # Sidebar
    st.sidebar.metric("TOTAL IMPACT", f"{total_impact_lbs:,.1f} lbs")
    st.sidebar.markdown("---")
    st.sidebar.write("### Computer's Data Check")
    # If you see names here instead of 'Unknown', it's fixed!
    st.sidebar.write(debug_df[['pantry_name', 'weight']].head(15))

    # Main UI
    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def generate_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=12, tiles="cartodbpositron")
        
        # Heatmap
        heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Marker Labels (Name + Weight)
        for _, row in df.iterrows():
            label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=label
            ).add_to(m)
        return m

    st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

    if st.button("Refresh Data Now"):
        st.cache_data.clear()
        st.rerun()

except Exception as e:
    st.error(f"Critical Error: {e}")

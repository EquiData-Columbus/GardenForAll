import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb
import re

st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Fetch Pantry Coordinates
    pantry_res = supabase.table("Pantry").select("pantry_name, location").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. Fetch Shipments - WE ARE CHANGING THIS SELECT
    # If pantry_name is a link, we need to ensure we get the string
    shipment_res = supabase.table("Food Shipments").select("weight, pantry_name").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # --- COORDINATE PROCESSING ---
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # --- THE "FORCE STRING" FIX ---
    # Sometimes Supabase returns a dictionary {'pantry_name': 'NNEMAP'} 
    # instead of just 'NNEMAP'. This flattens it.
    def flatten_column(val):
        if isinstance(val, dict):
            return list(val.values())[0]
        return str(val)

    shipment_df['pantry_name'] = shipment_df['pantry_name'].apply(flatten_column)
    pantry_df['pantry_name'] = pantry_df['pantry_name'].apply(flatten_column)

    # 3. CLEANING KEYS
    def clean_name(name):
        return re.sub(r'[^a-zA-Z0-9]', '', str(name)).lower()

    pantry_df['match_key'] = pantry_df['pantry_name'].apply(clean_name)
    shipment_df['match_key'] = shipment_df['pantry_name'].apply(clean_name)

    # 4. MATH
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    total_lbs = shipment_df['weight'].sum()

    # 5. MERGE
    pantry_weights = shipment_df.groupby('match_key')['weight'].sum().reset_index()
    final_df = pd.merge(pantry_df, pantry_weights, on="match_key", how="left")
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, total_lbs, shipment_df

# Execute
map_data, total_impact_lbs, debug_shipments = get_live_data()

# --- SIDEBAR DEBUGGING (Crucial) ---
st.sidebar.metric("TOTAL IMPACT", f"{total_impact_lbs:,.1f} lbs")
st.sidebar.subheader("Computer's View")
# This shows you exactly what the code thinks the pantry names are
st.sidebar.write(debug_shipments[['pantry_name', 'weight']].head(10))

# --- MAP ---
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

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

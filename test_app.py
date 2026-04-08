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

    # 1. Fetch tables
    pantry_res = supabase.table("Pantry").select("*").execute()
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    
    pantry_df = pd.DataFrame(pantry_res.data)
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

    # --- MATCHING LOGIC (RESTORED) ---
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # Bridge IDs to Names if they are missing
    pantry_map = dict(zip(pantry_df.index, pantry_df['pantry_name'])) 
    
    if shipment_df['pantry_name'].isnull().all():
        shipment_df['pantry_name'] = shipment_df.index.map(pantry_map)

    # 2. AGGREGATE: Sum weights by name so markers show the full total
    pantry_weights = shipment_df.groupby('pantry_name')['weight'].sum().reset_index()
    
    # 3. FINAL MERGE for the map
    final_df = pd.merge(pantry_df, pantry_weights, on='pantry_name', how='left')
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, shipment_df['weight'].sum(), pantry_weights

# --- UI EXECUTION ---
map_data, total_lbs, summary_df = get_live_data()

# Sidebar: Cleaned to show only Name and Weight
st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
st.sidebar.write("### Delivery Summary")
st.sidebar.dataframe(summary_df[['pantry_name', 'weight']], hide_index=True)

st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    # Center on Columbus
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap Layer
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers Layer
    for _, row in df.iterrows():
        label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=label
        ).add_to(m)
    return m

st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

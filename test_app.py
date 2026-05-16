import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# --- 1. Page Configuration ---
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

# --- 2. Data Pipeline ---
@st.cache_data(ttl=600)
def get_live_data():
    # Connect to Supabase
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # Fetch raw data
    pantry_res = supabase.table("Pantry").select("*").execute()
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    
    pantry_df = pd.DataFrame(pantry_res.data)
    shipment_df = pd.DataFrame(shipment_res.data)

    # Clean Pantry Data (Extract Lat/Lon from wkb hex)
    pantry_df = pantry_df.dropna(subset=['location'])
    
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x 
        except Exception: 
            return None, None
            
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(
        lambda x: pd.Series(parse_location(x))
    )
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # Clean Shipment Data & Calculate Weights
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # Group deliveries directly by the pantry_name foreign key
    pantry_weights = shipment_df.groupby('pantry_name', as_index=False)['weight'].sum()
    
    # Merge directly on the pantry_name column
    final_df = pd.merge(pantry_df, pantry_weights, on='pantry_name', how='left')
    final_df['weight'] = final_df['weight'].fillna(0) 

    total_lbs = shipment_df['weight'].sum()
    
    return final_df, total_lbs

# --- 3. UI and Display ---
# Load the data
map_data, total_lbs = get_live_data()

# Sidebar: Impact Metrics & Summary Table
st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
st.sidebar.write("### Delivery Summary")

# Sort the summary so the highest weights are at the top
summary_display = map_data[['pantry_name', 'weight']].sort_values(by='weight', ascending=False)
st.sidebar.dataframe(summary_display, hide_index=True)

# Main Title
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

# Map Generation Logic
def generate_map(df):
    # Base map centered on Columbus, Ohio
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Filter for heat points (only locations with actual weight)
    active_pantries = df[df['weight'] > 0]
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in active_pantries.iterrows()]
    
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Add markers for all pantries
    for _, row in df.iterrows():
        label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=label
        ).add_to(m)
        
    return m

# Render the map
st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

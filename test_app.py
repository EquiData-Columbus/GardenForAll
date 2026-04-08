import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb
from branca.element import Template, MacroElement

# Standard Setup
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")
st.sidebar.caption("Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))

@st.cache_data(ttl=600)
def get_live_data():
    # ... [Fetch your 3 tables here] ...

    # 1. Prepare Shipments (The Math)
    # Normalize product keys
    product_df['prod_key'] = product_df['product_name'].astype(str).str.lower().str.strip()
    shipment_df['prod_key'] = shipment_df['product_name'].astype(str).str.lower().str.strip()

    # Join Shipments to Products
    shipment_math = pd.merge(shipment_df, product_df[['prod_key', 'servings_per_lb']], on="prod_key", how="left")
    
    # Force numeric values
    shipment_math['weight'] = pd.to_numeric(shipment_math['weight'], errors='coerce').fillna(0)
    shipment_math['servings_per_lb'] = pd.to_numeric(shipment_math['servings_per_lb'], errors='coerce').fillna(1)
    
    # Calculate Total Servings per row
    shipment_math['total_servings'] = shipment_math['weight'] * shipment_math['servings_per_lb']

    # 2. Sum by Pantry Name (The Bridge)
    # Normalize pantry keys
    shipment_math['match_key'] = shipment_math['pantry_name'].astype(str).str.lower().str.strip()
    pantry_totals = shipment_math.groupby('match_key')['total_servings'].sum().reset_index()

    # 3. Prepare Map Pins
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip()
    
    # Merge totals into the pantry list
    final_df = pd.merge(pantry_df, pantry_totals, on="match_key", how="left")
    final_df['total_servings'] = final_df['total_servings'].fillna(0)

    # 4. Handle Coordinates LAST
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None

    final_df[['latitude', 'longitude']] = final_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    
    # We keep rows even if they have 0 servings, but they MUST have coordinates
    final_df = final_df.dropna(subset=['latitude', 'longitude'])

    return final_df, shipment_math['total_servings'].sum()
    
# Execute data pull
merged_data, total_impact = get_live_data()

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")

    # Only include markers/heatmap for rows with actual servings to keep it clean
    heat_data = [[row['latitude'], row['longitude'], row['total_servings']] for _, row in df.iterrows() if row['total_servings'] > 0]
    
    if heat_data:
        HeatMap(heat_data, radius=40, blur=15, max_zoom=13, gradient={0.2: 'blue', 0.5: 'yellow', 1.0: 'red'}).add_to(m)

    for _, row in df.iterrows():
        hover_text = f"<b>{row['pantry_name']}</b>: {row['total_servings']:,.0f} servings"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=hover_text
        ).add_to(m)
        
    return m

# Streamlit UI
st.title("Garden For All | Live Distribution Heatmap 🌎📌")
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} servings")

map_object = generate_map(merged_data)
st_folium(map_object, width=1200, height=600, returned_objects=[])

if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

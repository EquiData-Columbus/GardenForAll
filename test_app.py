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
    # ... [Keep your fetch logic the same] ...

    # 1. Normalize Names for Matching (Lowercasing prevents "Kale" vs "kale" errors)
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].astype(str).str.lower().str.strip()
    
    product_df['prod_key'] = product_df['product_name'].astype(str).str.lower().str.strip()
    shipment_df['prod_key'] = shipment_df['product_name'].astype(str).str.lower().str.strip()

    # 2. Merge Shipments with Products
    all_shipments = pd.merge(
        shipment_df, 
        product_df[['prod_key', 'servings_per_lb']], 
        on="prod_key", 
        how="left"
    )

    # 3. Secure the Math
    all_shipments['weight'] = pd.to_numeric(all_shipments['weight'], errors='coerce').fillna(0)
    
    # If a product isn't found, default to 1 serving so we at least see the weight on the map
    all_shipments['servings_per_lb'] = pd.to_numeric(all_shipments['servings_per_lb'], errors='coerce').fillna(1)
    all_shipments['total_servings'] = all_shipments['weight'] * all_shipments['servings_per_lb']

    # 4. Aggregate by the normalized match_key
    pantry_impact = all_shipments.groupby('match_key')['total_servings'].sum().reset_index()

    # 5. Final Merge back to coordinates
    final_df = pd.merge(pantry_df, pantry_impact, on="match_key", how="left")
    final_df['total_servings'] = final_df['total_servings'].fillna(0)

    return final_df, all_shipments['total_servings'].sum()
    
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

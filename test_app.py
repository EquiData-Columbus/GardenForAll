import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# 1. Setup & API Connection
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")
st.sidebar.caption("Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # Fetch data from Supabase
    pantry_res = supabase.table("Pantry").select("*").execute()
    pantry_df = pd.DataFrame(pantry_res.data)
    
    product_res = supabase.table("Product").select("*").execute()
    product_df = pd.DataFrame(product_res.data)
    
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # 2. Coordinate Processing
    # Convert hex location to Lat/Long
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None

    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 3. Data Normalization (The Bridge)
    # Force lowercase and strip whitespace so "NAFP" matches "nafp"
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].astype(str).str.lower().str.strip()
    
    product_df['prod_key'] = product_df['product_name'].astype(str).str.lower().str.strip()
    shipment_df['prod_key'] = shipment_df['product_name'].astype(str).str.lower().str.strip()

    # 4. Calculation Logic
    # Link Shipments to Products to get servings_per_lb
    shipment_math = pd.merge(shipment_df, product_df[['prod_key', 'servings_per_lb']], on="prod_key", how="left")
    
    # Ensure columns are numeric
    shipment_math['weight'] = pd.to_numeric(shipment_math['weight'], errors='coerce').fillna(0)
    # Default to 1 so weight isn't zeroed out if the product is missing in the Product table
    shipment_math['servings_per_lb'] = pd.to_numeric(shipment_math['servings_per_lb'], errors='coerce').fillna(1)
    shipment_math['total_servings'] = shipment_math['weight'] * shipment_math['servings_per_lb']

    # 5. Aggregation
    # Group by pantry key to get total servings per location
    pantry_impact = shipment_math.groupby('match_key')['total_servings'].sum().reset_index()

    # Merge totals into the coordinate dataframe
    final_df = pd.merge(pantry_df, pantry_impact, on="match_key", how="left")
    final_df['total_servings'] = final_df['total_servings'].fillna(0)

    # We return the mapped data and the total sum for the sidebar
    return final_df, shipment_math['total_servings'].sum()

# 6. Run Data Pipeline
merged_data, total_impact = get_live_data()https://github.com/EquiData-Columbus/GardenForAll/blob/main/test_app.py

# 7. Map Construction
def generate_map(df):
    # Center on Columbus, OH
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")

    # Filter for heatmap (only locations with > 0 servings)
    heat_data = [[row['latitude'], row['longitude'], row['total_servings']] for _, row in df.iterrows() if row['total_servings'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Add Markers
    for _, row in df.iterrows():
        hover_text = f"<b>{row['pantry_name']}</b>: {row['total_servings']:,.0f} servings"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=hover_text
        ).add
return m

# 8. Streamlit Interface
st.title("Garden For All | Live Distribution Heatmap 🌎📌")
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} servings")

# Display Map
map_object = generate_map(merged_data)
st_folium(map_object, width=1200, height=600, returned_objects=[])

# Refresh functionality
if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

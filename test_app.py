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

url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

st.sidebar.caption("Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))

@st.cache_data(ttl=600)
def get_live_data():
    # 1. Fetch data
    pantry_res = supabase.table("Pantry").select("*").execute()
    pantry_df = pd.DataFrame(pantry_res.data)
    product_res = supabase.table("Product").select("*").execute()
    product_df = pd.DataFrame(product_res.data)
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # 2. Process Coordinates
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 3. Create the Master Calculation Table
    # Merge shipments with products to get multipliers for EVERY row (even NULL pantries)
    all_shipments = pd.merge(shipment_df, product_df[['product_name', 'servings_per_lb']], on="product_name", how="left")
    
    # Ensure math works for everything
    all_shipments['weight'] = pd.to_numeric(all_shipments['weight'], errors='coerce').fillna(0)
    all_shipments['servings_per_lb'] = pd.to_numeric(all_shipments['servings_per_lb'], errors='coerce').fillna(0)
    all_shipments['total_servings'] = all_shipments['weight'] * all_shipments['servings_per_lb']

    # 4. Total Sidebar Impact (Sum of ALL rows, including NULLs)
    total_impact_all_time = all_shipments['total_servings'].sum()

    # 5. Pantry-Specific Impact (Sum for the markers)
    # We strip NULLs here so they don't create a "NaN" group
    pantry_impact = all_shipments.dropna(subset=['pantry_name']).groupby('pantry_name')['total_servings'].sum().reset_index()

    # 6. Final Merge to Pins
    final_df = pd.merge(pantry_df, pantry_impact, on="pantry_name", how="left")
    final_df['total_servings'] = final_df['total_servings'].fillna(0)    

    return final_df, total_impact_all_time
    
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

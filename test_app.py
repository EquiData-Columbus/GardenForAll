import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# 1. Setup
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # Fetch Data
    pantry_df = pd.DataFrame(supabase.table("Pantry").select("*").execute().data)
    product_df = pd.DataFrame(supabase.table("Product").select("*").execute().data)
    shipment_df = pd.DataFrame(supabase.table("Food Shipments").select("*").execute().data)

    # 2. Process Coordinates
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 3. Calculation for Sidebar Total ONLY
    # We do the math here just for that one big number
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    # Match shipments to products to get the serving multiplier
    shipment_math = pd.merge(
        shipment_df, 
        product_df[['product_name', 'servings_per_lb']], 
        on="product_name", 
        how="left"
    )
    shipment_math['servings_per_lb'] = pd.to_numeric(shipment_math['servings_per_lb'], errors='coerce').fillna(1)
    shipment_math['total_servings'] = shipment_math['weight'] * shipment_math['servings_per_lb']
    
    total_val = shipment_math['total_servings'].sum()

    # 4. Aggregation for the Sidebar Table
    # We use the raw shipment names here to avoid coordinate issues
    leaderboard = shipment_math.groupby('pantry_name')['total_servings'].sum().reset_index()
    leaderboard = leaderboard.sort_values(by='total_servings', ascending=False)

    return pantry_df, total_val, leaderboard

# Execute Pull
map_data, total_impact, leaderboard_df = get_live_data()

# 5. Sidebar UI
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} servings")
st.sidebar.markdown("---")
st.sidebar.subheader("Distribution Breakdown")
# Show the table without formatting if it's struggling
st.sidebar.table(leaderboard_df.set_index('pantry_name'))

# 6. Main Map UI
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    # Center on Columbus
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Markers (NAMES ONLY on hover)
    for _, row in df.iterrows():
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{row['pantry_name']}</b>"  # Removed the servings number
        ).add_to(m)
    return m

map_obj = generate_map(map_data)
st_folium(map_obj, width=1200, height=600, returned_objects=[])

if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

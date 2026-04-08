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

    # 3. Clean Keys for Matching (Standardization)
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].astype(str).str.lower().str.strip()
    
    product_df['prod_key'] = product_df['product_name'].astype(str).str.lower().str.strip()
    shipment_df['prod_key'] = shipment_df['product_name'].astype(str).str.lower().str.strip()

    # 4. Calculation with NaN Protection
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # Merge shipments with products
    shipment_math = pd.merge(shipment_df, product_df[['prod_key', 'servings_per_lb']], on="prod_key", how="left")
    
    # THE FIX: If product isn't found, default to 1 serving per lb so math doesn't break
    shipment_math['servings_per_lb'] = pd.to_numeric(shipment_math['servings_per_lb'], errors='coerce').fillna(1.0)
    shipment_math['total_servings'] = shipment_math['weight'] * shipment_math['servings_per_lb']
    
    # Total for Sidebar
    total_val = shipment_math['total_servings'].sum()

    # 5. Aggregation for Table and Map
    pantry_sums = shipment_math.groupby('match_key')['total_servings'].sum().reset_index()
    
    # Merge sums into the coordinate data
    final_map_df = pd.merge(pantry_df, pantry_sums, on="match_key", how="left")
    final_map_df['total_servings'] = final_map_df['total_servings'].fillna(0)

    return final_map_df, total_val, shipment_math

# Execute
map_data, total_impact, raw_math = get_live_data()

# 6. Sidebar UI
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} servings")
st.sidebar.markdown("---")
st.sidebar.subheader("Distribution Breakdown")

# Breakdown Table (Group by original name for readability)
leaderboard = raw_math.groupby('pantry_name')['total_servings'].sum().reset_index()
leaderboard = leaderboard[leaderboard['total_servings'] > 0].sort_values(by='total_servings', ascending=False)
st.sidebar.table(leaderboard.set_index('pantry_name'))

# 7. Main Map
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap
    heat_data = [[row['latitude'], row['longitude'], row['total_servings']] for _, row in df.iterrows() if row['total_servings'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers (NAMES ONLY as requested)
    for _, row in df.iterrows():
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{row['pantry_name']}</b>"
        ).add_to(m)
    return m

st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

if st.button("Refresh Data"):
    st.cache_data.clear()
    st.rerun()

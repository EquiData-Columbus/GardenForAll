import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# 1. Setup
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")
st.sidebar.caption("Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # Fetch Data
    pantry_df = pd.DataFrame(supabase.table("Pantry").select("*").execute().data)
    product_df = pd.DataFrame(supabase.table("Product").select("*").execute().data)
    shipment_df = pd.DataFrame(supabase.table("Food Shipments").select("*").execute().data)

    # 2. Prepare Coordinates
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 3. Clean Keys (Standardization)
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].astype(str).str.lower().str.strip()
    
    product_df['prod_key'] = product_df['product_name'].astype(str).str.lower().str.strip()
    shipment_df['prod_key'] = shipment_df['product_name'].astype(str).str.lower().str.strip()

    # 4. Calculation (The Bridge)
    shipment_math = pd.merge(shipment_df, product_df[['prod_key', 'servings_per_lb']], on="prod_key", how="left")
    
    # Ensure numbers are actual numbers
    shipment_math['weight'] = pd.to_numeric(shipment_math['weight'], errors='coerce').fillna(0)
    shipment_math['servings_per_lb'] = pd.to_numeric(shipment_math['servings_per_lb'], errors='coerce').fillna(1)
    shipment_math['total_servings'] = shipment_math['weight'] * shipment_math['servings_per_lb']

    # 5. Aggregation (Sum by Pantry)
    pantry_sums = shipment_math.groupby('match_key')['total_servings'].sum().reset_index()

    # 6. Final Merge for Map
    final_df = pd.merge(pantry_df, pantry_sums, on="match_key", how="left")
    final_df['total_servings'] = final_df['total_servings'].fillna(0)

    # Return Map Data AND the Shipment Math for the leaderboard
    return final_df, shipment_math

# Execute Pull
merged_data, raw_shipments = get_live_data()
total_impact = raw_shipments['total_servings'].sum()

# 7. Sidebar Leaderboard (The "Proof" Table)
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} servings")
st.sidebar.markdown("---")
st.sidebar.subheader("Distribution Breakdown")

# Create a clean summary for the sidebar
# We use pantry_name from shipments to show items even if they have no map coordinates
leaderboard = raw_shipments.groupby('pantry_name')['total_servings'].sum().reset_index()
leaderboard = leaderboard[leaderboard['total_servings'] > 0].sort_values(by='total_servings', ascending=False)

# Display as table
st.sidebar.table(leaderboard.set_index('pantry_name').style.format("{:,.0f}"))

# 8. Main Map UI
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap
    heat_data = [[row['latitude'], row['longitude'], row['total_servings']] for _, row in df.iterrows() if row['total_servings'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers
    for _, row in df.iterrows():
        val = row['total_servings']
        hover_text = f"<b>{row['pantry_name']}</b>: {val:,.0f} servings"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=hover_text
        ).add_to(m)
    return m

map_obj = generate_map(merged_data)
st_folium(map_obj, width=1200, height=600, returned_objects=[])

if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

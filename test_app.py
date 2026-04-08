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

    # Fetch Data - We only strictly need Pantry and Food Shipments now
    pantry_df = pd.DataFrame(supabase.table("Pantry").select("*").execute().data)
    shipment_df = pd.DataFrame(supabase.table("Food Shipments").select("*").execute().data)

    # 2. Process Coordinates
    pantry_df = pantry_df.dropna(subset=['location']) #
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 3. Clean Keys for Matching
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip() #
    shipment_df['match_key'] = shipment_df['pantry_name'].astype(str).str.lower().str.strip() #

    # 4. Calculation (Pounds Only)
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0) #
    
    # Total for Sidebar
    total_lbs = shipment_df['weight'].sum()

    # 5. Aggregation
    pantry_weights = shipment_df.groupby('match_key')['weight'].sum().reset_index()
    
    # Merge weights into the coordinate data
    final_map_df = pd.merge(pantry_df, pantry_weights, on="match_key", how="left")
    final_map_df['weight'] = final_map_df['weight'].fillna(0)

    return final_map_df, total_lbs, shipment_df

# Execute
map_data, total_impact, raw_shipments = get_live_data()

# 6. Sidebar UI
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} lbs") # Changed label to lbs
st.sidebar.markdown("---")
st.sidebar.subheader("Distribution Breakdown (lbs)")

# Breakdown Table
leaderboard = raw_shipments.groupby('pantry_name')['weight'].sum().reset_index()
leaderboard = leaderboard[leaderboard['weight'] > 0].sort_values(by='weight', ascending=False)
st.sidebar.table(leaderboard.set_index('pantry_name'))

# 7. Main Map
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap (Using weight for intensity)
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers (NAMES ONLY on hover)
    for _, row in df.iterrows():
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{row['pantry_name']}</b>" #
        ).add_to(m)
    return m

st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

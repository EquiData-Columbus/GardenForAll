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

    # 1. Fetch Pantry Data (Coordinates and Names)
    pantry_res = supabase.table("Pantry").select("*").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. Fetch Shipment Data
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # 3. Process Coordinates
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 4. THE FIX: Create a direct lookup for the Foreign Key
    # This maps whatever ID Supabase is sending to the actual text name
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # We force both columns to strings to ensure the match works
    pantry_df['pantry_name_str'] = pantry_df['pantry_name'].astype(str)
    shipment_df['pantry_name_str'] = shipment_df['pantry_name'].astype(str)

    # 5. Aggregate Weights by the string version of the name
    pantry_weights = shipment_df.groupby('pantry_name_str')['weight'].sum().reset_index()
    
    # 6. Final Merge
    final_df = pd.merge(
        pantry_df, 
        pantry_weights, 
        left_on='pantry_name_str', 
        right_on='pantry_name_str', 
        how='left'
    )
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, shipment_df['weight'].sum(), shipment_df

# --- UI EXECUTION ---
map_data, total_lbs, debug_df = get_live_data()

# Sidebar Debugging
st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
st.sidebar.write("### Data Check")
# This will now show the actual ID or Name being sent by Supabase
st.sidebar.write(debug_df[['pantry_name', 'weight']].head(10))

st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    for _, row in df.iterrows():
        # Displaying the text name and final weight on markers
        label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=label
        ).add_to(m)
    return m

st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

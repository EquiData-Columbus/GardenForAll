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

    # 1. Fetch Pantry Table
    pantry_res = supabase.table("Pantry").select("pantry_name, location").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. Fetch Shipments - CRITICAL CHANGE
    # If 'pantry_name' is a relation, this select tells Supabase: 
    # "Get the weight, and go into the linked table to get the text name"
    shipment_res = supabase.table("Food Shipments").select("weight, pantry_name").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # --- COORDINATE PROCESSING ---
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # --- THE "NONE" FIX ---
    # If Supabase returns an object/ID, we force it back to a string 
    # so it matches the names on the map pins.
    def force_string(val):
        if isinstance(val, dict):
            return str(next(iter(val.values())))
        return str(val)

    shipment_df['pantry_name'] = shipment_df['pantry_name'].apply(force_string)
    pantry_df['pantry_name'] = pantry_df['pantry_name'].apply(force_string)

    # 3. CLEANING & MATH
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    total_lbs = shipment_df['weight'].sum()

    # Match keys (standardize for the merge)
    pantry_df['match_key'] = pantry_df['pantry_name'].str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].str.lower().str.strip()

    # 4. GROUP AND MERGE
    pantry_weights = shipment_df.groupby('match_key')['weight'].sum().reset_index()
    final_df = pd.merge(pantry_df, pantry_weights, on="match_key", how="left")
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, total_lbs, shipment_df

# Execute
map_data, total_impact_lbs, debug_df = get_live_data()

# SIDEBAR (For validation)
st.sidebar.metric("TOTAL IMPACT", f"{total_impact_lbs:,.1f} lbs")
st.sidebar.write("### Data Check")
# If this still says 'None', we know the issue is the Supabase Column Name
st.sidebar.write(debug_df[['pantry_name', 'weight']].head(10))

# MAIN MAP
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    for _, row in df.iterrows():
        # Labels are back!
        label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=label
        ).add_to(m)
    return m

st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

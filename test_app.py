import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

st.set_page_config(page_title="Garden For All | Final Fix", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Get Pantries (The Map Pins)
    p_res = supabase.table("Pantry").select("*").execute()
    p_df = pd.DataFrame(p_res.data)

    # 2. Get All Shipments (The Weights)
    s_res = supabase.table("Food Shipments").select("*").execute()
    s_df = pd.DataFrame(s_res.data)

    # Clean the weight column immediately
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 3. Handle Coordinates
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df = p_df.dropna(subset=['location'])
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 4. MANUAL OVERRIDE LOOP (The "Inefficient" but safe way)
    # We create a new list for the final weights
    final_pantry_weights = []

    for index, pantry in p_df.iterrows():
        pantry_name = str(pantry['pantry_name'])
        pantry_id = str(pantry.get('id', index)) # Use index if ID column is missing
        
        # We look for matches in shipments using BOTH name and ID
        # This ensures we catch every "Motherful" and every "7"
        total_found = 0
        for _, shipment in s_df.iterrows():
            ship_ref = str(shipment['pantry_name'])
            if ship_ref == pantry_name or ship_ref == pantry_id:
                total_found += shipment['weight']
        
        final_pantry_weights.append(total_found)

    p_df['summed_weight'] = final_pantry_weights

    # Prepare a simple summary for the sidebar
    summary_df = p_df[['pantry_name', 'summed_weight']].copy()
    summary_df.columns = ['Pantry', 'Lbs']

    return p_df, s_df['weight'].sum(), summary_df

try:
    map_df, total_lbs, side_table = get_live_data()

    # Sidebar
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(side_table.sort_values(by='Lbs', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap (Using the manually summed weights)
    heat_data = [[r['lat'], r['lon'], r['summed_weight']] for _, r in map_df.iterrows() if r['summed_weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers (Showing the full manually calculated total)
    for _, r in map_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['summed_weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Manual Sync Error: {e}")

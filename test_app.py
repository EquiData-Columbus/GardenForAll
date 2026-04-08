import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

st.set_page_config(page_title="Garden For All | Final Map", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Fetch raw data as simple objects
    p_data = supabase.table("Pantry").select("*").execute().data
    s_data = supabase.table("Food Shipments").select("*").execute().data
    
    p_df = pd.DataFrame(p_data)
    s_df = pd.DataFrame(s_data)

    # 2. Fix Weights & Coordinates
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)
    
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 3. MANUAL OVERRIDE: The "Inefficient" but Guaranteed Sum
    # We iterate through every pantry and manually search the shipments
    summed_results = []
    
    # Identify the ID column dynamically to avoid the Sync Error
    potential_id_cols = [c for c in p_df.columns if c.lower() in ['id', 'pantry_id', 'uuid']]
    id_col = potential_id_cols[0] if potential_id_cols else p_df.columns[0]

    for _, pantry in p_df.iterrows():
        name = str(pantry['pantry_name']).strip().lower()
        p_id = str(pantry[id_col]).strip().lower()
        
        # Manually add up every shipment that matches this name OR this ID
        pantry_total = 0
        for _, ship in s_df.iterrows():
            ship_ref = str(ship['pantry_name']).strip().lower()
            if ship_ref == name or ship_ref == p_id:
                pantry_total += ship['weight']
        
        summed_results.append(pantry_total)

    p_df['total_weight'] = summed_results
    
    # Prepare Sidebar Data
    sidebar_summary = p_df[p_df['total_weight'] > 0][['pantry_name', 'total_weight']]
    sidebar_summary.columns = ['Pantry', 'Lbs Delivered']

    return p_df, s_df['weight'].sum(), sidebar_summary

try:
    final_df, total_lbs, side_table = get_live_data()

    # Sidebar: Shows accurate multiple sums
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Breakdown")
    st.sidebar.table(side_table.sort_values(by='Lbs Delivered', ascending=False))

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap Layer
    heat_data = [[r['lat'], r['lon'], r['total_weight']] for _, r in final_df.iterrows() if r['total_weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Pins: Now showing correctly summed weights for each location
    for _, r in final_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['total_weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Display Error: {e}. Checking database link columns...")

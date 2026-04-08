import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

st.set_page_config(page_title="Garden For All | Map", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Fetch raw data
    p_res = supabase.table("Pantry").select("*").execute()
    s_res = supabase.table("Food Shipments").select("*").execute()
    
    p_df = pd.DataFrame(p_res.data)
    s_df = pd.DataFrame(s_res.data)

    # 2. Fix Coordinates
    p_df = p_df.dropna(subset=['location'])
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 3. Simple Weight Conversion
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 4. Simple Merge (No Summing)
    # This just grabs the first weight found for each pantry name.
    map_data = pd.merge(p_df, s_df[['pantry_name', 'weight']], on='pantry_name', how='left')
    map_data['weight'] = map_data['weight'].fillna(0)

    return map_data, s_df['weight'].sum()

# --- UI EXECUTION ---
try:
    final_df, total_lbs = get_live_data()

    # Sidebar Metric
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    
    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def create_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
        
        # Heatmap Layer
        heat_data = [[r['lat'], r['lon'], r['weight']] for _, r in df.iterrows() if r['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Markers showing the first weight value found
        for _, r in df.iterrows():
            tooltip = f"<b>{r['pantry_name']}</b>: {r['weight']:.1f} lbs"
            folium.Marker(
                location=[r['lat'], r['lon']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=tooltip
            ).add_to(m)
        return m

    st_folium(create_map(final_df), width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Error: {e}")

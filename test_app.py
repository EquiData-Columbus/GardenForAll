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

    # 1. Fetch the raw data tables
    pantry_res = supabase.table("Pantry").select("*").execute()
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    
    p_df = pd.DataFrame(pantry_res.data)
    s_df = pd.DataFrame(shipment_res.data)

    # 2. Brute-force weight calculation
    # We turn everything into a number so we can do math
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 3. Coordinate Processing
    p_df = p_df.dropna(subset=['location'])
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 4. THE FIX: SUM EVERYTHING FIRST
    # We add up every delivery for each location so Motherful shows a big number
    summary = s_df.groupby('pantry_name')['weight'].sum().reset_index()

    # 5. Final Merge
    # We join the big weights to the map coordinates
    map_df = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_df['weight'] = map_df['weight'].fillna(0)

    return map_df, s_df['weight'].sum(), summary

# --- UI EXECUTION ---
try:
    map_data, total_lbs, summary_df = get_live_data()

    # Sidebar: Total Impact and the clean table
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    # Sort by weight so the biggest contributors are at the top
    st.sidebar.dataframe(summary_df.sort_values(by='weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def generate_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
        
        # Heatmap (Density based on the SUMMED weights)
        heat_data = [[row['lat'], row['lon'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Markers showing the accurate total weight for each site
        for _, row in df.iterrows():
            label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
            folium.Marker(
                location=[row['lat'], row['lon']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=label
            ).add_to(m)
        return m

    st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"App Error: {e}")

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

    # 1. Fetch raw data
    p_data = supabase.table("Pantry").select("*").execute().data
    s_data = supabase.table("Food Shipments").select("*").execute().data
    p_df = pd.DataFrame(p_data)
    s_df = pd.DataFrame(s_data)

    # 2. Fix Weights (Force the 4,798.1 lbs total)
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 3. Fix Coordinates
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    
    p_df = p_df.dropna(subset=['location'])
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 4. HARD-CODE THE BRIDGE (The ID Error Fix)
    # We find the ID column even if it's hidden or named differently
    id_col = 'id' if 'id' in p_df.columns else p_df.columns[0] 
    
    # Create a translator: { "7": "Motherful", "12": "NNEMAP" }
    id_to_name = dict(zip(p_df[id_col].astype(str), p_df['pantry_name']))

    # 5. TRANSLATE AND SUM (The 0.0 lbs Fix)
    # We turn the numbers in shipments into names so the math actually groups together
    s_df['clean_name'] = s_df['pantry_name'].astype(str).map(id_to_name).fillna(s_df['pantry_name'].astype(str))
    
    summary = s_df.groupby('clean_name')['weight'].sum().reset_index()
    summary.columns = ['pantry_name', 'weight']

    # 6. Final Join for Map
    map_data = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_data['weight'] = map_data['weight'].fillna(0)

    return map_data, s_df['weight'].sum(), summary

try:
    final_df, total_impact, side_table = get_live_data()

    # Sidebar Metric and Table
    st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(side_table.sort_values(by='weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    # Center map on Columbus
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap Layer
    heat_data = [[r['lat'], r['lon'], r['weight']] for _, r in final_df.iterrows() if r['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Marker Pins with Correct Summed Totals
    for _, r in final_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Client Display Error: {e}")

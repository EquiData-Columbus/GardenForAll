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
    p_df = pd.DataFrame(supabase.table("Pantry").select("*").execute().data)
    s_df = pd.DataFrame(supabase.table("Food Shipments").select("*").execute().data)

    # 2. Fix Coordinates
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 3. Force weights to numbers
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 4. THE BRUTE FORCE BRIDGE (The Fix)
    # We create a map of "Whatever ID is here" -> "The Pantry Name"
    # We use the index as a backup if 'id' is missing
    p_df['link_id'] = p_df['id'].astype(str) if 'id' in p_df.columns else p_df.index.astype(str)
    id_to_name = dict(zip(p_df['link_id'], p_df['pantry_name']))
    
    # Translate shipments: ID numbers become real names
    s_df['pantry_id_str'] = s_df['pantry_name'].astype(str)
    s_df['real_name'] = s_df['pantry_id_str'].map(id_to_name).fillna(s_df['pantry_id_str'])

    # 5. THE TOTAL SUM (Gets the full 4,798.1 lbs)
    summary = s_df.groupby('real_name')['weight'].sum().reset_index()
    summary.columns = ['pantry_name', 'weight']

    # 6. Final Join
    map_data = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_data['weight'] = map_data['weight'].fillna(0)

    return map_data, s_df['weight'].sum(), summary

try:
    final_df, total_lbs, side_table = get_live_data()

    # Sidebar: Accurate Total
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(side_table.sort_values(by='weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap (Summed Weight)
    heat_data = [[r['lat'], r['lon'], r['weight']] for _, r in final_df.iterrows() if r['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Pins (Corrected Names and Weights)
    for _, r in final_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Error: {e}")

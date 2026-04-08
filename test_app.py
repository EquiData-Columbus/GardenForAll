import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

st.set_page_config(page_title="Garden For All | Final Dashboard", layout="wide")

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

    # 3. THE BRIDGE: Map IDs to Names
    # We turn the Pantry ID column into a dictionary so we can look up names
    # Using .get() prevents the 'id' syntax error you saw earlier
    id_to_name = dict(zip(p_df['id'].astype(str), p_df['pantry_name']))

    # 4. SUM THE WEIGHTS (The 4,798.1 lbs Fix)
    # We translate the shipments table IDs into Names, then SUM
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)
    s_df['mapped_name'] = s_df['pantry_name'].astype(str).map(id_to_name).fillna(s_df['pantry_name'])
    
    summary = s_df.groupby('mapped_name')['weight'].sum().reset_index()
    summary.columns = ['pantry_name', 'total_weight']

    # 5. Final Join for Map
    map_data = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_data['total_weight'] = map_data['total_weight'].fillna(0)

    return map_data, s_df['weight'].sum(), summary

try:
    final_df, total_lbs, side_table = get_live_data()

    # Sidebar: Total Impact
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(side_table.sort_values(by='total_weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap Layer (Using the new Summed Weights)
    heat_data = [[r['lat'], r['lon'], r['total_weight']] for _, r in final_df.iterrows() if r['total_weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Pin Markers showing TRUE totals
    for _, r in final_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['total_weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Sync Error: {e}. Ensure 'id' and 'pantry_name' exist in your Pantry table.")

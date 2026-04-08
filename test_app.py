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

    # 3. OVERRIDE: Clean weights and link IDs
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)
    
    # Create a translator for IDs to Names
    # We force 'id' and 'pantry_name' to strings so they MUST match
    id_to_name = dict(zip(p_df['id'].astype(str), p_df['pantry_name'].astype(str)))
    
    # Create the "Clean Name" column in shipments
    def get_real_name(val):
        val_str = str(val)
        return id_to_name.get(val_str, val_str) # Use the name if ID found, else keep original val

    s_df['final_name'] = s_df['pantry_name'].apply(get_real_name)

    # 4. SUM EVERYTHING (The Math Fix)
    summary = s_df.groupby('final_name')['weight'].sum().reset_index()
    summary.columns = ['pantry_name', 'weight']

    # 5. FINAL MERGE
    # We merge the summed weights back to the pantry list
    map_data = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_data['weight'] = map_data['weight'].fillna(0)

    return map_data, s_df['weight'].sum(), summary

try:
    final_df, total_weight, side_table = get_live_data()

    # Sidebar
    st.sidebar.metric("TOTAL IMPACT", f"{total_weight:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(side_table.sort_values(by='weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap
    heat_data = [[r['lat'], r['lon'], r['weight']] for _, r in final_df.iterrows() if r['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers
    for _, r in final_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Sync Error: {e}")

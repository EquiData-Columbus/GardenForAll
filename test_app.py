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
    p_res = supabase.table("Pantry").select("*").execute()
    s_res = supabase.table("Food Shipments").select("*").execute()
    
    p_df = pd.DataFrame(p_res.data)
    s_df = pd.DataFrame(s_res.data)

    # 2. Fix Weights (The NaN Problem)
    # We force weights to numbers so math actually happens
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 3. Fix Coordinates
    p_df = p_df.dropna(subset=['location'])
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 4. THE LINK FIX (Brute Force Mapping)
    # We create a simple dictionary of {ID: Name} from your Pantry table
    # We use 'id' if it exists, otherwise we use the row index
    if 'id' in p_df.columns:
        id_map = dict(zip(p_df['id'], p_df['pantry_name']))
    else:
        id_map = p_df['pantry_name'].to_dict()

    # Apply the real name to every single shipment
    s_df['real_pantry_name'] = s_df['pantry_name'].map(id_map)

    # 5. THE SUM FIX (No more tiny values)
    # We sum all shipments by name BEFORE merging with the map
    summary = s_df.groupby('real_pantry_name')['weight'].sum().reset_index()
    summary.columns = ['pantry_name', 'weight']

    # 6. Final Join
    map_data = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_data['weight'] = map_data['weight'].fillna(0)

    return map_data, s_df['weight'].sum(), summary

# --- UI DISPLAY ---
try:
    final_df, total_weight, side_table = get_live_data()

    # Sidebar Metric and Table
    st.sidebar.metric("TOTAL IMPACT", f"{total_weight:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(side_table.sort_values(by='weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def create_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
        
        # Heatmap Layer (Uses full summed weight)
        heat_data = [[r['lat'], r['lon'], r['weight']] for _, r in df.iterrows() if r['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Pins with True Totals
        for _, r in df.iterrows():
            popup_text = f"<b>{r['pantry_name']}</b>: {r['weight']:,.1f} lbs"
            folium.Marker(
                location=[r['lat'], r['lon']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=popup_text
            ).add_to(m)
        return m

    st_folium(create_map(final_df), width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Data Connection Error: {e}")

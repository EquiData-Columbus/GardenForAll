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

    # 1. Fetch tables
    pantry_res = supabase.table("Pantry").select("*").execute()
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    
    p_df = pd.DataFrame(pantry_res.data)
    s_df = pd.DataFrame(shipment_res.data)

    # 2. Force Weight to Numbers
    s_df['weight'] = pd.to_numeric(s_df['weight'], errors='coerce').fillna(0)

    # 3. COORDINATE BRUTE FORCE
    p_df = p_df.dropna(subset=['location'])
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 4. BRUTE FORCE SUMMING (The Fix for tiny 2.7 lbs values)
    # We link the tables by the ID number and then sum every single shipment
    # This ensures the 4,798.1 lbs is actually used.
    combined = pd.merge(s_df, p_df[['id', 'pantry_name']], left_on='pantry_name', right_on='id', suffixes=('_id', '_name'))
    
    # Create the final summary table
    summary = combined.groupby('pantry_name_name')['weight'].sum().reset_index()
    summary.columns = ['pantry_name', 'weight']

    # 5. Final Merge for Map
    map_df = pd.merge(p_df, summary, on='pantry_name', how='left')
    map_df['weight'] = map_df['weight'].fillna(0)

    return map_df, s_df['weight'].sum(), summary

# --- UI EXECUTION ---
try:
    map_data, total_lbs, summary_df = get_live_data()

    # Sidebar: Total Impact and the requested table
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    st.sidebar.dataframe(summary_df.sort_values(by='weight', ascending=False), hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def generate_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
        
        # Heatmap (True Density)
        heat_data = [[row['lat'], row['lon'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Markers (Summed Totals)
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
    st.error(f"Data Error: {e}. Please check if the 'Pantry' table has 'id' and 'pantry_name' columns.")

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

    # 1. Fetch raw data as simple lists
    pantry_data = supabase.table("Pantry").select("*").execute().data
    shipment_data = supabase.table("Food Shipments").select("*").execute().data
    
    p_df = pd.DataFrame(pantry_data)
    s_df = pd.DataFrame(shipment_data)

    # 2. Coordinate Processing
    def parse_loc(val):
        try:
            pt = wkb.loads(val, hex=True)
            return pt.y, pt.x
        except: return None, None
    p_df[['lat', 'lon']] = p_df['location'].apply(lambda x: pd.Series(parse_loc(x)))
    p_df = p_df.dropna(subset=['lat', 'lon'])

    # 3. THE RAW SUM OVERRIDE (Manual Loop)
    # We create a dictionary to hold our totals
    manual_totals = {}

    for shipment in shipment_data:
        # Get weight (force to float)
        try:
            w = float(shipment.get('weight', 0))
        except:
            w = 0
            
        # Get the pantry reference (could be a name or an ID)
        ref = str(shipment.get('pantry_name', 'Unknown'))
        
        # Add to the total bucket
        manual_totals[ref] = manual_totals.get(ref, 0) + w

    # 4. BRUTE FORCE MATCHING
    # We look at every pantry and try to find its weight in our buckets
    final_weights = []
    for _, row in p_df.iterrows():
        p_name = str(row['pantry_name'])
        p_id = str(row.get('id', ''))
        
        # Check if the weight was stored under the Name OR the ID
        weight = manual_totals.get(p_name, 0) + manual_totals.get(p_id, 0)
        final_weights.append(weight)

    p_df['total_weight'] = final_weights

    # Total for Sidebar
    total_impact = sum(manual_totals.values())
    
    return p_df, total_impact

try:
    map_df, total_lbs = get_live_data()

    # Sidebar
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    # Clean table for client
    st.sidebar.table(map_df[map_df['total_weight'] > 0][['pantry_name', 'total_weight']].sort_values(by='total_weight', ascending=False))

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap
    heat_data = [[r['lat'], r['lon'], r['total_weight']] for _, r in map_df.iterrows() if r['total_weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Pins
    for _, r in map_df.iterrows():
        folium.Marker(
            location=[r['lat'], r['lon']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=f"<b>{r['pantry_name']}</b>: {r['total_weight']:,.1f} lbs"
        ).add_to(m)

    st_folium(m, width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Manual Sync Error: {e}")

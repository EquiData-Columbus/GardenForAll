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
    
    pantry_df = pd.DataFrame(pantry_res.data)
    shipment_df = pd.DataFrame(shipment_res.data)

    # 2. Process Coordinates
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 3. ACCURATE SUMMING LOGIC
    # First, convert weight to numbers
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # Identify the Link: Supabase usually stores the 'id' of the pantry in the 'pantry_name' column
    # We create a dictionary where {ID: "Name"}
    # Check if 'id' exists in pantry_df, if not use index as ID
    id_col = 'id' if 'id' in pantry_df.columns else pantry_df.index
    id_to_name = dict(zip(pantry_df[id_col], pantry_df['pantry_name']))

    # Translate the IDs in shipment_df to actual names
    # We apply the map to the column that currently contains the numbers/None
    shipment_df['actual_name'] = shipment_df['pantry_name'].map(id_to_name)

    # 4. AGGREGATE: Sum every single shipment for each location
    # This is what ensures 'Motherful' reflects all deliveries
    summary_df = shipment_df.groupby('actual_name')['weight'].sum().reset_index()
    summary_df.columns = ['pantry_name', 'weight']

    # 5. FINAL MERGE for the map
    final_df = pd.merge(pantry_df, summary_df, on='pantry_name', how='left')
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, shipment_df['weight'].sum(), summary_df

# --- UI EXECUTION ---
map_data, total_lbs, summary_df = get_live_data()

# Sidebar: Cleaned to show only Name and Weight
st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
st.sidebar.write("### Delivery Summary")
st.sidebar.dataframe(summary_df.sort_values(by='weight', ascending=False), hide_index=True)

st.title("Garden For All | Live Distribution Heatmap 🌎📌")

def generate_map(df):
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap Layer (Reflects true summed density)
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers Layer with accurate totals
    for _, row in df.iterrows():
        label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=label
        ).add_to(m)
    return m

st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

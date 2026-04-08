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

    # 1. Fetch Pantry table - This is our "Translator"
    pantry_res = supabase.table("Pantry").select("*").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. Fetch Shipments table
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # --- COORDINATE PROCESSING ---
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # --- THE NONE-KILLER: MANUAL TRANSLATION ---
    # Convert weight to numbers
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # We pull the real names from the Pantry table and match them to the Shipments
    # even if Supabase is sending IDs or empty names.
    # We match based on the 'pantry_name' column which acts as the shared ID.
    combined_data = pd.merge(
        shipment_df[['weight', 'pantry_name']], 
        pantry_df[['pantry_name', 'latitude', 'longitude']], 
        on='pantry_name', 
        how='inner' # Only keep matches that actually have coordinates
    )

    # 3. AGGREGATE TOTALS
    # This ensures "Motherful" shows the sum of all shipments, not just 2.7 lbs
    summary_df = combined_data.groupby('pantry_name')['weight'].sum().reset_index()
    
    # 4. FINAL MAP DATA
    # Re-attach coordinates to the summed weights
    map_final = pd.merge(summary_df, pantry_df[['pantry_name', 'latitude', 'longitude']], on='pantry_name')

    return map_final, shipment_df['weight'].sum(), summary_df

# --- EXECUTION ---
try:
    map_data, total_lbs, summary_table = get_live_data()

    # Sidebar
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Delivery Summary")
    # Clean table showing only Name and Total Weight
    st.sidebar.dataframe(summary_table[['pantry_name', 'weight']], hide_index=True)

    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def generate_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
        
        # Heatmap
        heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows()]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Markers
        for _, row in df.iterrows():
            label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs total"
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=label
            ).add_to(m)
        return m

    st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Waiting for valid data link... (Error: {e})")

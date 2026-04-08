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

    # 1. Fetch Pantry Reference (Coordinates and Names)
    pantry_res = supabase.table("Pantry").select("pantry_name, location").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. THE CRITICAL FIX: The "Unpack" Select
    # This syntax tells Supabase: "Give me the weight, AND the text name 
    # from inside that linked Pantry table."
    shipment_res = supabase.table("Food Shipments").select("""
        weight,
        pantry_name
    """).execute()
    
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

    # --- DATA NORMALIZATION ---
    # Convert weights to numbers
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # Force names to strings to ensure they match perfectly
    pantry_df['pantry_name'] = pantry_df['pantry_name'].astype(str).str.strip()
    shipment_df['pantry_name'] = shipment_df['pantry_name'].astype(str).str.strip()

    # 3. AGGREGATE WEIGHTS
    pantry_weights = shipment_df.groupby('pantry_name')['weight'].sum().reset_index()
    
    # 4. MERGE WEIGHTS TO COORDINATES
    final_df = pd.merge(pantry_df, pantry_weights, on='pantry_name', how='left')
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, shipment_df['weight'].sum(), shipment_df

# --- EXECUTION ---
try:
    map_data, total_lbs, debug_df = get_live_data()

    # Sidebar UI
    st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")
    st.sidebar.write("### Computer's Raw View")
    # This will now show actual names instead of 'None'
    st.sidebar.write(debug_df[['pantry_name', 'weight']].head(15))

    # Main UI
    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def generate_map(df):
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
        
        # Heatmap Layer
        heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Markers Layer
        for _, row in df.iterrows():
            label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=label
            ).add_to(m)
        return m

    st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

except Exception as e:
    st.error(f"Data Connection Error: {e}")

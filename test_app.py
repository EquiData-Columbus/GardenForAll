import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# 1. Page Configuration
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 2. Fetch Pantry Coordinates
    pantry_res = supabase.table("Pantry").select("pantry_name, location").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 3. Fetch Shipments with a JOIN
    # This syntax grabs the weight and the name from the linked Pantry table
    shipment_res = supabase.table("Food Shipments").select("""
        weight,
        pantry_name:Pantry(pantry_name)
    """).execute()
    
    raw_data = shipment_res.data
    
    # 4. Flatten the Joined Data
    # Unpacks the nested dictionary {'pantry_name': {'pantry_name': 'NNEMAP'}}
    flattened_shipments = []
    for row in raw_data:
        pantry_info = row.get('pantry_name')
        name = "Unknown"
        
        if isinstance(pantry_info, dict):
            name = pantry_info.get('pantry_name', "Unknown")
        elif isinstance(pantry_info, str):
            name = pantry_info
            
        flattened_shipments.append({
            'weight': row.get('weight', 0),
            'pantry_name': name
        })
    
    shipment_df = pd.DataFrame(flattened_shipments)

    # 5. Coordinate Processing (WKB to Lat/Long)
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
        
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(
        lambda x: pd.Series(parse_location(x))
    )
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # 6. Math & Merging
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    total_lbs = shipment_df['weight'].sum()

    # Standardize keys for matching
    pantry_df['match_key'] = pantry_df['pantry_name'].astype(str).str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].astype(str).str.lower().str.strip()

    # Sum weights by pantry
    pantry_weights = shipment_df.groupby('match_key')['weight'].sum().reset_index()
    
    # Final Join for the Map
    final_df = pd.merge(pantry_df, pantry_weights, on="match_key", how="left")
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, total_lbs, shipment_df

# --- EXECUTION ---
try:
    map_data, total_impact_lbs, debug_df = get_live_data()

    # 7. Sidebar Metrics & Debugging
    st.sidebar.metric("TOTAL IMPACT", f"{total_impact_lbs:,.1f} lbs")
    st.sidebar.markdown("---")
    st.sidebar.write("### Computer's Data Check")
    # This confirms the 'None' issue is resolved
    st.sidebar.write(debug_df[['pantry_name', 'weight']].head(15))

    # 8. Main Map UI
    st.title("Garden For All | Live Distribution Heatmap 🌎📌")

    def generate_map(df):
        # Center on Columbus, OH
        m = folium.Map(location=[39.9612, -82.9988], zoom_start=12, tiles="cartodbpositron")
        
        # Heatmap Layer (Weight based intensity)
        heat_data = [[row['latitude'], row['longitude'], row['weight']] 
                     for _, row in df.iterrows() if row['weight'] > 0]
        if heat_data:
            HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

        # Markers with Name + Weight labels
        for _, row in df.iterrows():
            label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
            folium.Marker(
                location=[row['latitude'], row['longitude']],
                icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
                tooltip=label
            ).add_to(m)
        return m

    st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

    if st.button("Refresh Data Now"):
        st.cache_data.clear()
        st.rerun()

except Exception as e:
    st.error(f"Error connecting to data: {e}")
    st.write("Please check your Supabase credentials and column names.")

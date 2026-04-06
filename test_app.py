# import streamlit as st
# from st_supabase_connection import SupabaseConnection

# # Initialize connection.
# conn = st.connection("supabase",type=SupabaseConnection)

# # Perform query.
# rows = conn.table("Product").select("*").execute()

# # Print every product name.
# i=1
# for row in rows.data:
#     name = row["product_name"]
#     st.write(f"Product {i}: {name}")
#     i += 1

import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd

#Add title
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

#Connect the supabase data using streamlit secrets key and url
SUPABASE_URL = "https://asopyqavtaihknofbufu.supabase.co"
SUPABASE_KEY = "sb_publishable_KpAmy6gIlTXiC5HuZdCmrw_QVrvKWl9"
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

st.sidebar.caption("Last checked: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
#This allows us to get the data but this only happens every ten minutes to stop sensitive keys
@st.cache_data(ttl=600)
def get_live_data():
    # Pull pantry data
    pantry_res = supabase.table("food_pantry").select("*").execute()
    df = pd.DataFrame(pantry_res.data)
    
    #Cleaning (Handles strings/commas from DB if not already numeric)
    df['Weight (lbs)'] = df['Weight (lbs)'].astype(str).str.replace(',', '').apply(pd.to_numeric, errors='coerce').fillna(0)
    
    #Pull Coordinates
    loc_res = supabase.table("locations").select("*").execute()
    loc_df = pd.DataFrame(loc_res.data)
    
    # Merge data so Weights and Lat/Long are in one dataframe
    return pd.merge(df, loc_df, left_on='Food Pantry', right_on='name', how='inner')

merged_data = get_live_data()

#Generate the actual map
def generate_map(df):
    # Center on Columbus
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")

    # Apply custom "Olive/Green" CSS filter
    map_filter = """
    <style>
        .leaflet-tile-container { filter: sepia(100%) hue-rotate(35deg) saturate(150%) brightness(90%) contrast(90%); }
        .leaflet-container { background: #9ab643 !important; }
    </style>
    """
    m.get_root().header.add_child(folium.Element(map_filter))

    #Heatmap Layer
    heat_data = [[row['latitude'], row['longitude'], row['Weight (lbs)']] for _, row in df.iterrows()]
    HeatMap(heat_data, radius=40, blur=15, max_zoom=13).add_to(m)

    #Markers with Tooltips
    for _, row in df.iterrows():
        hover_text = f"<b>{row['Food Pantry']}</b>: {row['Weight (lbs)']:,.0f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkgreen', icon='shopping-cart', prefix='fa'),
            tooltip=hover_text
        ).add_to(m)
    
    return m

#Streamlit UI
st.title("Live Distribution Heatmap")
st.markdown("This map updates automatically as new data is entered into the database.")

#Extra key
total_impact = merged_data['Weight (lbs)'].sum()
st.sidebar.metric("2025 TOTAL IMPACT", f"{total_impact:,.1f} lbs")

# Display the Map
map_object = generate_map(merged_data)
st_folium(map_object, width=1200, height=600, returned_objects=[])

if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

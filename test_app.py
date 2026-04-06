import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

#Add title
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

#Connect the supabase data using streamlit secrets key and url
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

st.sidebar.caption("Last checked: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
#This allows us to get the data but this only happens every ten minutes to stop sensitive keys
@st.cache_data(ttl=600)
def get_live_data():
    # Pull pantry data
    pantry_res = supabase.table("Pantry").select("*").execute()
    df = pd.DataFrame(pantry_res.data)
    
    # Cleaning (Handles strings/commas from DB if not already numeric)
    df['Weight (lbs)'] = 1 
    
    pantry_res = supabase.table("Pantry").select("*").execute()
    df = pd.DataFrame(pantry_res.data)
    
    #Filter out rows where location is NULL
    df = df.dropna(subset=['location'])

    #Convert PostGIS Hex to Lat/Long
    def parse_location(hex_val):
        try:
            #Load the point from the hex string
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x  # y is lat, x is lon
        except:
            return None, None

    df[['latitude', 'longitude']] = df['location'].apply(
        lambda x: pd.Series(parse_location(x))
    )

    #Remove any that failed to parse
    df = df.dropna(subset=['latitude', 'longitude'])
    
    df['Weight (lbs)'] = 1 
    return df
    
    # Merge data so Weights and Lat/Long are in one dataframe
    # return pd.merge(df, loc_df, left_on='Pantry', right_on='name', how='inner')
    return df

merged_data = get_live_data()

#Generate the actual map
def generate_map(df):
    #Center at Columbus
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
        # Using 'pantry_name' based on your Database Diagnostic
        hover_text = f"<b>{row['pantry_name']}</b>: {row['Weight (lbs)']:,.0f} units"
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

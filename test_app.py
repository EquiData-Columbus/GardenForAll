import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb

# Set up the web page layout to be wide and give it a title
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

# This "cache" function tells the app to remember the data for 10 minutes (600 seconds) 
# so it doesn't have to keep bugging the database every time you click something.
@st.cache_data(ttl=600)
def get_live_data():
    # Grab the secret "keys" to the database from the settings file
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Fetch tables: Pull the 'Pantry' list and the 'Food Shipments' history
    pantry_res = supabase.table("Pantry").select("*").execute()
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    
    # Convert that raw database data into organized tables (like Excel sheets)
    pantry_df = pd.DataFrame(pantry_res.data)
    shipment_df = pd.DataFrame(shipment_res.data)

    # --- COORDINATE PROCESSING ---
    # Throw out any pantries that don't have a location set so the map doesn't crash
    pantry_df = pantry_df.dropna(subset=['location'])
    
    # The database stores locations in a weird 'hex' code. This turns that code
    # into standard Latitude and Longitude numbers that a map can read.
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x # Return Latitude, Longitude
        except: return None, None
        
    # Apply that conversion to every row in our pantry list
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    
    # Remove anyone who still has missing coordinates after the conversion
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # --- MATCHING LOGIC (RESTORED) ---
    # Make sure the 'weight' column is treated as a number. If there's a typo, 
    # treat it as 0 instead of breaking the math.
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    
    # Sometimes the database uses ID numbers instead of names. This "Bridge" 
    # creates a dictionary to translate those numbers back into real pantry names.
    pantry_map = dict(zip(pantry_df.index, pantry_df['pantry_name'])) 
    
    # If the names are missing in the shipment logs, use that dictionary to fill them in
    if shipment_df['pantry_name'].isnull().all():
        shipment_df['pantry_name'] = shipment_df.index.map(pantry_map)

    # 2. AGGREGATE: This is the important part. It groups every single delivery 
    # for "Motherful" (for example) and adds the weights together so we see 
    # the total impact, not just one delivery at a time.
    pantry_weights = shipment_df.groupby('pantry_name')['weight'].sum().reset_index()
    
    # 3. FINAL MERGE: Combine the pantry coordinates with the calculated weights.
    # We use a 'left' merge so that if a pantry has 0 deliveries, it still shows up.
    final_df = pd.merge(pantry_df, pantry_weights, on='pantry_name', how='left')
    final_df['weight'] = final_df['weight'].fillna(0) # Change 'Nothing' to '0'

    return final_df, shipment_df['weight'].sum(), pantry_weights

# --- UI EXECUTION (Building the actual website) ---
# Run the logic above to get our clean data
map_data, total_lbs, summary_df = get_live_data()

# Sidebar: Create the big "Impact" number at the top left
st.sidebar.metric("TOTAL IMPACT", f"{total_lbs:,.1f} lbs")

# Sidebar: Create a simple table showing how much each place got
st.sidebar.write("### Delivery Summary")
st.sidebar.dataframe(summary_df[['pantry_name', 'weight']], hide_index=True)

# Main Title
st.title("Garden For All | Live Distribution Heatmap 🌎📌")

# The function that actually draws the map
def generate_map(df):
    # Start the map centered on Columbus, Ohio
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")
    
    # Heatmap Layer: This adds the "glow" based on how heavy the deliveries are
    heat_data = [[row['latitude'], row['longitude'], row['weight']] for _, row in df.iterrows() if row['weight'] > 0]
    if heat_data:
        HeatMap(heat_data, radius=35, blur=15, max_zoom=13).add_to(m)

    # Markers Layer: Put a blue shopping cart pin at every location
    for _, row in df.iterrows():
        # This is what pops up when you hover over a pin
        label = f"<b>{row['pantry_name']}</b>: {row['weight']:,.1f} lbs"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=label
        ).add_to(m)
    return m

# Display the map on the website
st_folium(generate_map(map_data), width=1200, height=600, returned_objects=[])

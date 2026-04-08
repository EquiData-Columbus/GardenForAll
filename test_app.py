import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from supabase import create_client
import pandas as pd
from shapely import wkb
from branca.element import Template, MacroElement

#Add title
st.set_page_config(page_title="Garden For All | Live Heatmap", layout="wide")

#Connect the supabase data using streamlit secrets key and url
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]
supabase = create_client(url, key)

st.sidebar.caption("Last updated: " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"))
#This allows us to get the data but this only happens every ten minutes to stop sensitive keys
@st.cache_data(ttl=600)
def get_live_data():
    # Pull pantry data
    pantry_res = supabase.table("Pantry").select("*").execute()
    pantry_df = pd.DataFrame(pantry_res.data)
    
    # Filter out rows where location is NULL
    pantry_df = pantry_df.dropna(subset=['location'])

    # Convert PostGIS Hex to Lat/Long
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except:
            return None, None

    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(
        lambda x: pd.Series(parse_location(x))
    )
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # Pull product and shipment data
    product_res = supabase.table("Product").select("*").execute()
    product_df = pd.DataFrame(product_res.data)
    
    shipment_res = supabase.table("Food Shipments").select("*").execute()
    shipment_df = pd.DataFrame(shipment_res.data)

    # --- FIX START: Handle NULL pantry names ---
    # We temporarily fill NULL pantry names so the groupby doesn't ignore them
    shipment_df['pantry_name'] = shipment_df['pantry_name'].fillna("Unassigned")
    # --- FIX END ---

    # Merge shipments with product data
    merged = pd.merge(shipment_df, product_df, on="product_name", how="left")
    
    # Ensure math columns are numbers
    merged['weight'] = pd.to_numeric(merged['weight'], errors='coerce').fillna(0)
    merged['servings_per_lb'] = pd.to_numeric(merged['servings_per_lb'], errors='coerce').fillna(0)
    
    # Calculate impact
    merged['total_servings'] = merged['weight'] * merged['servings_per_lb']
        
    # Group by pantry (Now includes "Unassigned" instead of dropping NULLs)
    pantry_impact = merged.groupby('pantry_name')['total_servings'].sum().reset_index()

    # Final merge: Link calculated servings back to coordinates
    final_df = pd.merge(pantry_df, pantry_impact, on="pantry_name", how="left")
    final_df['total_servings'] = final_df['total_servings'].fillna(0)    

    return final_df, merged['total_servings'].sum()

# Execute data pull
merged_data, total_impact = get_live_data()

#Generate the actual map
def generate_map(df):
    #Center at Columbus
    m = folium.Map(location=[39.9612, -82.9988], zoom_start=11, tiles="cartodbpositron")

    #Heatmap Layer
    # Using total_servings for the intensity weight
    heat_data = [[row['latitude'], row['longitude'], row['total_servings']] for _, row in df.iterrows()]
    HeatMap(heat_data, radius=40, blur=15, max_zoom=13, gradient={0.2: 'blue', 0.5: 'yellow', 1.0: 'red'}).add_to(m)

    #Markers with Tooltips
    for _, row in df.iterrows():
        # Using 'pantry_name' based on your Database Diagnostic
        # Tooltip displays the specific serving count linked to this marker
        hover_text = f"<b>{row['pantry_name']}</b>: {row['total_servings']:,.0f} servings"
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            icon=folium.Icon(color='darkblue', icon='shopping-cart', prefix='fa'),
            tooltip=hover_text
        ).add_to(m)
        
    # Adding a Custom HTML Legend for the Heatmap
    legend_html = """
    {% macro html(this, kwargs) %}
    <div style="
        position: fixed; 
        bottom: 50px; left: 50px; width: 160px; height: 100px; 
        background-color: white; border:2px solid grey; z-index:9999; font-size:14px;
        border-radius: 6px; padding: 10px;
        ">
        <b>Distribution Impact</b><br>
        <i style="background:red; width:10px; height:10px; float:left; margin-right:5px; margin-top:3px;"></i> High Density<br>
        <i style="background:orange; width:10px; height:10px; float:left; margin-right:5px; margin-top:3px;"></i> Medium<br>
        <i style="background:blue; width:10px; height:10px; float:left; margin-right:5px; margin-top:3px;"></i> Low Density<br>
    </div>
    {% endmacro %}
    """
    legend = MacroElement()
    legend._template = Template(legend_html)
    m.get_root().add_child(legend)
    
    return m

#Streamlit UI
st.title("Garden For All | Live Distribution Heatmap 🌎📌")
st.markdown("This map updates automatically as new data is entered into the database.")

# Display the impact metric in the sidebar
st.sidebar.metric("TOTAL IMPACT", f"{total_impact:,.1f} servings")

# Display the Map
map_object = generate_map(merged_data)
st_folium(map_object, width=1200, height=600, returned_objects=[])

if st.button("Refresh Data Now"):
    st.cache_data.clear()
    st.rerun()

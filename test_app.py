@st.cache_data(ttl=600)
def get_live_data():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    supabase = create_client(url, key)

    # 1. Fetch Pantry Table normally
    pantry_res = supabase.table("Pantry").select("pantry_name, location").execute()
    pantry_df = pd.DataFrame(pantry_res.data)

    # 2. Fetch Shipments using a JOIN to get the actual text name
    # We ask for 'weight' and the 'pantry_name' from the related table
    # Adjust 'pantry_name' below if the foreign key column has a different ID name
    shipment_res = supabase.table("Food Shipments").select("""
        weight,
        pantry_name:Pantry(pantry_name)
    """).execute()
    
    raw_data = shipment_res.data
    
    # 3. Flatten the joined data
    # Supabase returns related data as a nested dictionary: {'pantry_name': {'pantry_name': 'NNEMAP'}}
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

    # --- COORDINATE PROCESSING ---
    pantry_df = pantry_df.dropna(subset=['location'])
    def parse_location(hex_val):
        try:
            point = wkb.loads(hex_val, hex=True)
            return point.y, point.x
        except: return None, None
    pantry_df[['latitude', 'longitude']] = pantry_df['location'].apply(lambda x: pd.Series(parse_location(x)))
    pantry_df = pantry_df.dropna(subset=['latitude', 'longitude'])

    # --- MATH & MERGE ---
    shipment_df['weight'] = pd.to_numeric(shipment_df['weight'], errors='coerce').fillna(0)
    total_lbs = shipment_df['weight'].sum()

    # Match keys
    pantry_df['match_key'] = pantry_df['pantry_name'].str.lower().str.strip()
    shipment_df['match_key'] = shipment_df['pantry_name'].str.lower().str.strip()

    pantry_weights = shipment_df.groupby('match_key')['weight'].sum().reset_index()
    final_df = pd.merge(pantry_df, pantry_weights, on="match_key", how="left")
    final_df['weight'] = final_df['weight'].fillna(0)

    return final_df, total_lbs, shipment_df

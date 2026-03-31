import streamlit as st
from st_supabase_connection import SupabaseConnection

# Initialize connection.
conn = st.connection("supabase",type=SupabaseConnection)

# Perform query.
rows = conn.table("Product").select("*").execute()

Print every product name.
i=1
for row in rows.data:
    name = row["product_name"]
    st.write(f"Product {i}: {name}")
    i += 1


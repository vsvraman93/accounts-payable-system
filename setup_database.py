import os
import sqlite3
import streamlit as st

def setup_database():
    # Database path
    DB_PATH = "accounts_payable.db"
    
    # Create necessary directories
    os.makedirs("database", exist_ok=True)
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("reports", exist_ok=True)
    os.makedirs("static/img", exist_ok=True)
    
    # Schema path
    schema_path = os.path.join("database", "schema.sql")
    
    # Check if schema file exists
    if not os.path.exists(schema_path):
        st.error(f"Schema file not found at {schema_path}")
        st.info("Please create the schema.sql file in the database directory")
        return False
    
    # Create/connect to database
    conn = sqlite3.connect(DB_PATH)
    
    try:
        # Execute schema file
        with open(schema_path, 'r') as f:
            schema_sql = f.read()
            conn.executescript(schema_sql)
        
        # Verify tables were created
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [table[0] for table in cursor.fetchall() if not table[0].startswith('sqlite_')]
        
        # Print table list
        st.write(f"Created tables:")
        for table in tables:
            st.write(f"- {table}")
        
        st.success(f"Database setup complete! Created {len(tables)} tables.")
        return True
    
    except Exception as e:
        st.error(f"Error setting up database: {e}")
        return False
    
    finally:
        conn.close()

if __name__ == "__main__":
    import streamlit as st
    
    st.title("Database Setup Tool")
    st.write("This tool will create the SQLite database and all required tables.")
    
    if st.button("Initialize Database"):
        setup_database()
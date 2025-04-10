import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
import io
import numpy as np

# Database connection
DB_PATH = "accounts_payable.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_table_columns(table_name):
    """Get column names and types for a table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get column information
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    conn.close()
    
    return columns

def get_foreign_keys(table_name):
    """Get foreign key information for a table"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get foreign key information
    cursor.execute(f"PRAGMA foreign_key_list({table_name})")
    foreign_keys = cursor.fetchall()
    
    conn.close()
    
    return foreign_keys

def data_management():
    st.title("Data Management")
    
    # Get available tables
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [table[0] for table in cursor.fetchall()]
    conn.close()
    
    if not tables:
        st.warning("No tables found in the database. Please initialize the database first.")
        if st.button("Initialize Database"):
            from setup_database import setup_database
            setup_database()
        return
    
    # Table selection
    selected_table = st.selectbox("Select Table", tables)
    
    # Show table structure
    columns = get_table_columns(selected_table)
    foreign_keys = get_foreign_keys(selected_table)
    
    with st.expander("Table Structure"):
        # Display column information
        col_df = pd.DataFrame(columns, columns=["cid", "name", "type", "notnull", "dflt_value", "pk"])
        st.dataframe(col_df[["name", "type", "pk", "notnull"]])
        
        # Display foreign key information if any
        if foreign_keys:
            st.subheader("Foreign Keys")
            fk_df = pd.DataFrame(foreign_keys, columns=["id", "seq", "table", "from", "to", "on_update", "on_delete", "match"])
            st.dataframe(fk_df[["from", "table", "to"]])
    
    # Tabs for different operations
    tab1, tab2, tab3, tab4 = st.tabs(["View Data", "Add Record", "Edit/Delete", "Import/Export"])
    
    # Tab 1: View Data
    with tab1:
        st.subheader(f"Data in {selected_table}")
        
        # Fetch data
        conn = get_db_connection()
        try:
            df = pd.read_sql(f"SELECT * FROM {selected_table}", conn)
            if len(df) > 0:
                st.dataframe(df)
                st.write(f"Total records: {len(df)}")
            else:
                st.info(f"No records found in table '{selected_table}'")
        except Exception as e:
            st.error(f"Error fetching data: {e}")
        finally:
            conn.close()
    
    # Tab 2: Add Record
    with tab2:
        st.subheader(f"Add New Record to {selected_table}")
        
        with st.form(f"add_record_form_{selected_table}"):
            # Create form fields based on columns
            form_values = {}
            
            for col in columns:
                col_name = col["name"]
                col_type = col["type"].upper()
                is_pk = col["pk"] == 1
                
                # Skip primary key if it's autoincrement
                if is_pk and "INTEGER" in col_type and col_name.endswith("_id"):
                    continue
                
                # Handle foreign keys with dropdown
                fk_match = next((fk for fk in foreign_keys if fk["from"] == col_name), None)
                
                if fk_match:
                    # Provide dropdown for foreign key
                    ref_table = fk_match["table"]
                    ref_col = fk_match["to"]
                    
                    conn = get_db_connection()
                    try:
                        # Get display column (assume it's the second column for simplicity)
                        cursor = conn.cursor()
                        cursor.execute(f"PRAGMA table_info({ref_table})")
                        ref_cols = cursor.fetchall()
                        display_col = ref_cols[1]["name"] if len(ref_cols) > 1 else ref_col
                        
                        # Fetch options
                        options_df = pd.read_sql(
                            f"SELECT {ref_col}, {display_col} FROM {ref_table}",
                            conn
                        )
                        
                        if not options_df.empty:
                            # Create a dictionary for display
                            options_dict = dict(zip(options_df[ref_col], options_df[display_col]))
                            
                            # Add a blank option at the beginning
                            options = list(options_dict.keys())
                            options.insert(0, None)
                            
                            selected = st.selectbox(
                                f"{col_name}",
                                options=options,
                                format_func=lambda x: "" if x is None else f"{x} - {options_dict.get(x, '')}"
                            )
                            form_values[col_name] = selected
                        else:
                            st.warning(f"No options available for {col_name} (references {ref_table}.{ref_col})")
                            form_values[col_name] = st.text_input(f"{col_name}")
                    except Exception as e:
                        st.error(f"Error loading options for {col_name}: {e}")
                        form_values[col_name] = st.text_input(f"{col_name}")
                    finally:
                        conn.close()
                
                # Handle different column types
                elif "INT" in col_type:
                    form_values[col_name] = st.number_input(
                        f"{col_name}",
                        value=0,
                        step=1
                    )
                elif "DECIMAL" in col_type or "REAL" in col_type or "FLOAT" in col_type:
                    form_values[col_name] = st.number_input(
                        f"{col_name}",
                        value=0.0,
                        format="%.2f"
                    )
                elif "DATE" in col_type:
                    form_values[col_name] = st.date_input(f"{col_name}")
                elif "TIME" in col_type and "TIMESTAMP" not in col_type:
                    form_values[col_name] = st.time_input(f"{col_name}")
                elif "TIMESTAMP" in col_type:
                    # Default timestamp fields are usually auto-generated
                    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.text(f"{col_name}: {current_time} (Auto-generated)")
                    form_values[col_name] = current_time
                elif "BOOLEAN" in col_type:
                    form_values[col_name] = st.checkbox(f"{col_name}")
                else:
                    # Default to text input
                    form_values[col_name] = st.text_input(f"{col_name}")
            
            submitted = st.form_submit_button("Add Record")
            
            if submitted:
                # Filter out None values and empty auto-increment PKs
                filtered_values = {k: v for k, v in form_values.items() 
                                if v is not None and not (k.endswith("_id") and v == 0)}
                
                # Build SQL query
                columns_str = ", ".join(filtered_values.keys())
                placeholders = ", ".join(["?"] * len(filtered_values))
                
                # Insert the record
                conn = get_db_connection()
                try:
                    with conn:
                        conn.execute(
                            f"INSERT INTO {selected_table} ({columns_str}) VALUES ({placeholders})",
                            list(filtered_values.values())
                        )
                    st.success("Record added successfully!")
                    
                    # Log the action
                    user_id = st.session_state.get('user', {}).get('user_id')
                    if user_id:
                        conn.execute(
                            "INSERT INTO audit_logs (user_id, action, entity_type, details) VALUES (?, ?, ?, ?)",
                            (user_id, "added", selected_table, f"Added new record to {selected_table}")
                        )
                    conn.commit()
                except Exception as e:
                    st.error(f"Error adding record: {e}")
                finally:
                    conn.close()
    
    # Tab 3: Edit/Delete
    with tab3:
        st.subheader(f"Edit or Delete Records in {selected_table}")
        
        # Fetch data
        conn = get_db_connection()
        try:
            df = pd.read_sql(f"SELECT * FROM {selected_table}", conn)
            if len(df) == 0:
                st.info(f"No records found in table '{selected_table}'")
                return
                
            # Determine primary key
            primary_key = next((col["name"] for col in columns if col["pk"] == 1), None)
            
            if not primary_key:
                st.error(f"No primary key found for table '{selected_table}'")
                return
            
            # Select record to edit
            record_ids = df[primary_key].tolist()
            
            # Get a better display for the record selection
            display_col = df.columns[1] if len(df.columns) > 1 else primary_key
            record_display = [f"{row[primary_key]} - {row[display_col]}" for _, row in df.iterrows()]
            
            selected_record_idx = st.selectbox(
                "Select Record to Edit/Delete", 
                options=range(len(record_ids)),
                format_func=lambda x: record_display[x]
            )
            
            selected_record_id = record_ids[selected_record_idx]
            
            # Get the current record data
            record_data = df[df[primary_key] == selected_record_id].iloc[0].to_dict()
            
            # Edit form
            with st.form(f"edit_record_form_{selected_table}"):
                st.write(f"Editing record with {primary_key}: {selected_record_id}")
                
                # Create form fields based on columns
                form_values = {}
                
                for col in columns:
                    col_name = col["name"]
                    col_type = col["type"].upper()
                    is_pk = col["pk"] == 1
                    
                    # Display but disable primary key
                    if is_pk:
                        st.text_input(f"{col_name}", value=record_data[col_name], disabled=True)
                        form_values[col_name] = record_data[col_name]
                        continue
                    
                    # Handle foreign keys with dropdown
                    fk_match = next((fk for fk in foreign_keys if fk["from"] == col_name), None)
                    
                    if fk_match:
                        # Provide dropdown for foreign key
                        ref_table = fk_match["table"]
                        ref_col = fk_match["to"]
                        
                        try:
                            # Get display column (assume it's the second column for simplicity)
                            cursor = conn.cursor()
                            cursor.execute(f"PRAGMA table_info({ref_table})")
                            ref_cols = cursor.fetchall()
                            display_col = ref_cols[1]["name"] if len(ref_cols) > 1 else ref_col
                            
                            # Fetch options
                            options_df = pd.read_sql(
                                f"SELECT {ref_col}, {display_col} FROM {ref_table}",
                                conn
                            )
                            
                            if not options_df.empty:
                                # Create a dictionary for display
                                options_dict = dict(zip(options_df[ref_col], options_df[display_col]))
                                
                                # Find the current value in the options
                                current_value = record_data.get(col_name)
                                if current_value not in options_dict:
                                    options_dict[current_value] = f"Unknown ({current_value})"
                                
                                selected = st.selectbox(
                                    f"{col_name}",
                                    options=list(options_dict.keys()),
                                    format_func=lambda x: f"{x} - {options_dict.get(x, '')}",
                                    index=list(options_dict.keys()).index(current_value) if current_value in options_dict else 0
                                )
                                form_values[col_name] = selected
                            else:
                                form_values[col_name] = st.text_input(
                                    f"{col_name}", 
                                    value=record_data.get(col_name, "")
                                )
                        except Exception as e:
                            st.error(f"Error loading options for {col_name}: {e}")
                            form_values[col_name] = st.text_input(
                                f"{col_name}", 
                                value=record_data.get(col_name, "")
                            )
                    
                    # Handle different column types
                    elif "INT" in col_type:
                        form_values[col_name] = st.number_input(
                            f"{col_name}",
                            value=int(record_data.get(col_name, 0)),
                            step=1
                        )
                    elif "DECIMAL" in col_type or "REAL" in col_type or "FLOAT" in col_type:
                        form_values[col_name] = st.number_input(
                            f"{col_name}",
                            value=float(record_data.get(col_name, 0.0)),
                            format="%.2f"
                        )
                    elif "DATE" in col_type:
                        try:
                            date_value = pd.to_datetime(record_data.get(col_name)).date()
                        except:
                            date_value = datetime.now().date()
                        form_values[col_name] = st.date_input(f"{col_name}", value=date_value)
                    elif "BOOLEAN" in col_type:
                        form_values[col_name] = st.checkbox(
                            f"{col_name}", 
                            value=bool(record_data.get(col_name, False))
                        )
                    else:
                        # Default to text input
                        form_values[col_name] = st.text_input(
                            f"{col_name}", 
                            value=record_data.get(col_name, "")
                        )
                
                col1, col2 = st.columns(2)
                with col1:
                    update_submitted = st.form_submit_button("Update Record")
                with col2:
                    delete_submitted = st.form_submit_button("Delete Record")
                
                if update_submitted:
                    # Remove primary key from values to update
                    update_values = {k: v for k, v in form_values.items() if k != primary_key}
                    
                    # Build SQL query
                    set_clause = ", ".join(f"{key} = ?" for key in update_values.keys())
                    
                    # Update the record
                    try:
                        with conn:
                            conn.execute(
                                f"UPDATE {selected_table} SET {set_clause} WHERE {primary_key} = ?",
                                list(update_values.values()) + [selected_record_id]
                            )
                        st.success("Record updated successfully!")
                        
                        # Log the action
                        user_id = st.session_state.get('user', {}).get('user_id')
                        if user_id:
                            conn.execute(
                                "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)",
                                (user_id, "updated", selected_table, selected_record_id, f"Updated record in {selected_table}")
                            )
                        conn.commit()
                    except Exception as e:
                        st.error(f"Error updating record: {e}")
                
                if delete_submitted:
                    # Confirm deletion
                    if st.checkbox("Confirm deletion", key="confirm_deletion"):
                        try:
                            with conn:
                                conn.execute(
                                    f"DELETE FROM {selected_table} WHERE {primary_key} = ?",
                                    [selected_record_id]
                                )
                            st.success("Record deleted successfully!")
                            
                            # Log the action
                            user_id = st.session_state.get('user', {}).get('user_id')
                            if user_id:
                                conn.execute(
                                    "INSERT INTO audit_logs (user_id, action, entity_type, entity_id, details) VALUES (?, ?, ?, ?, ?)",
                                    (user_id, "deleted", selected_table, selected_record_id, f"Deleted record from {selected_table}")
                                )
                            conn.commit()
                        except Exception as e:
                            st.error(f"Error deleting record: {e}")
                    else:
                        st.warning("Please confirm deletion by checking the box")
        
        except Exception as e:
            st.error(f"Error: {e}")
        finally:
            conn.close()
    
    # Tab 4: Import/Export
    with tab4:
        st.subheader(f"Import/Export Data for {selected_table}")
        
        # Export data
        st.write("### Export Data")
        conn = get_db_connection()
        try:
            df = pd.read_sql(f"SELECT * FROM {selected_table}", conn)
            
            if len(df) > 0:
                csv = df.to_csv(index=False)
                excel_buffer = io.BytesIO()
                df.to_excel(excel_buffer, index=False)
                excel_buffer.seek(0)
                
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "Download as CSV",
                        data=csv,
                        file_name=f"{selected_table}.csv",
                        mime="text/csv"
                    )
                with col2:
                    st.download_button(
                        "Download as Excel",
                        data=excel_buffer,
                        file_name=f"{selected_table}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
            else:
                st.info(f"No data to export from table '{selected_table}'")
        except Exception as e:
            st.error(f"Error exporting data: {e}")
        finally:
            conn.close()
        
        # Import data
        st.write("### Import Data")
        upload_type = st.radio("Select file type", ["CSV", "Excel"])
        
        uploaded_file = st.file_uploader(
            f"Upload {'CSV' if upload_type == 'CSV' else 'Excel'} file", 
            type=['csv'] if upload_type == 'CSV' else ['xlsx', 'xls']
        )
        
        if uploaded_file is not None:
            try:
                if upload_type == 'CSV':
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.write("Preview of data to be imported:")
                st.dataframe(df.head())
                
                # Check if required columns exist
                table_columns = [col["name"] for col in columns]
                primary_key = next((col["name"] for col in columns if col["pk"] == 1), None)
                missing_columns = [col for col in table_columns if col not in df.columns and col != primary_key]
                
                if missing_columns:
                    st.warning(f"Missing columns in import file: {', '.join(missing_columns)}")
                
                # Options for import
                import_options = st.radio(
                    "Import options",
                    ["Append new records", "Replace all data in table (WARNING: This will delete existing records)"]
                )
                
                # Import button
                if st.button("Import Data"):
                    conn = get_db_connection()
                    try:
                        # Remove columns that don't exist in the table
                        df = df[[col for col in df.columns if col in table_columns]]
                        
                        if import_options == "Replace all data in table (WARNING: This will delete existing records)":
                            # Delete existing records
                            conn.execute(f"DELETE FROM {selected_table}")
                        
                        # Insert new records
                        for _, row in df.iterrows():
                            # Remove NaN values
                            row_dict = {k: v for k, v in row.items() if not pd.isna(v)}
                            
                            if row_dict:
                                columns_str = ", ".join(row_dict.keys())
                                placeholders = ", ".join(["?"] * len(row_dict))
                                
                                conn.execute(
                                    f"INSERT INTO {selected_table} ({columns_str}) VALUES ({placeholders})",
                                    list(row_dict.values())
                                )
                        
                        conn.commit()
                        st.success(f"Successfully imported {len(df)} records to {selected_table}!")
                        
                        # Log the action
                        user_id = st.session_state.get('user', {}).get('user_id')
                        if user_id:
                            conn.execute(
                                "INSERT INTO audit_logs (user_id, action, entity_type, details) VALUES (?, ?, ?, ?)",
                                (user_id, "imported", selected_table, f"Imported {len(df)} records to {selected_table}")
                            )
                            conn.commit()
                    
                    except Exception as e:
                        st.error(f"Error importing data: {e}")
                    finally:
                        conn.close()
            
            except Exception as e:
                st.error(f"Error reading file: {e}")

if __name__ == "__main__":
    st.set_page_config(page_title="Data Manager", layout="wide")
    data_management()
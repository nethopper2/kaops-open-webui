#!/usr/bin/env python3
"""
Query data source records from the database for debugging purposes.
This script connects to the database and displays data source information.
"""

import os
import sys
import json
from datetime import datetime

# Add the backend directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

def main():
    try:
        # Import the DataSources model
        from open_webui.models.data import DataSources
        
        # Get user ID from command line or use default
        if len(sys.argv) > 1:
            user_id = sys.argv[1]
        else:
            user_id = "7b3ffb6e-802b-4c08-b62c-b2af51bc96d6"  # Default user ID
        
        print(f"Querying data sources for user: {user_id}")
        print("=" * 80)
        
        # Query data sources
        data_sources = DataSources.get_data_sources_by_user_id(user_id)
        
        if not data_sources:
            print(f"No data sources found for user {user_id}")
            return
        
        print(f"Found {len(data_sources)} data source(s) for user {user_id}:")
        print("=" * 80)
        
        for ds in data_sources:
            print(f"ID: {ds.id}")
            print(f"User ID: {ds.user_id}")
            print(f"Name: {ds.name}")
            print(f"Context: {ds.context}")
            print(f"Sync Status: {ds.sync_status}")
            print(f"Last Sync: {ds.last_sync}")
            print(f"Files Processed: {ds.files_processed}")
            print(f"Files Total: {ds.files_total}")
            print(f"MB Processed: {ds.mb_processed}")
            print(f"MB Total: {ds.mb_total}")
            print(f"Sync Start Time: {ds.sync_start_time}")
            
            # Format sync_results for display
            if ds.sync_results:
                try:
                    if isinstance(ds.sync_results, str):
                        sync_results = json.loads(ds.sync_results)
                    else:
                        sync_results = ds.sync_results
                    print(f"Sync Results: {json.dumps(sync_results, indent=2)}")
                except:
                    print(f"Sync Results: {ds.sync_results}")
            else:
                print("Sync Results: None")
            
            print(f"Icon: {ds.icon}")
            print(f"Action: {ds.action}")
            print(f"Layer: {ds.layer}")
            print(f"Created At: {ds.created_at}")
            print(f"Updated At: {ds.updated_at}")
            print("-" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

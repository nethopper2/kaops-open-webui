#!/usr/bin/env python3
"""
Script to query the data_source table for Google Drive sources
"""

import sys
import os
import json

# Add the backend directory to the path so we can import the project modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from open_webui.models.data import DataSources

try:
    # Get data sources for specific user ID
    user_id = "7b3ffb6e-802b-4c08-b62c-b2af51bc96d6"
    user_sources = DataSources.get_data_sources_by_user_id(user_id)
    
    if not user_sources:
        print("No data sources found for user")
    else:
        print(f"Found {len(user_sources)} data source(s) for user {user_id}:")
        print("=" * 80)
        
        for ds in user_sources:
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
            print(f"Sync Results: {json.dumps(ds.sync_results, indent=2) if ds.sync_results else 'None'}")
            print(f"Icon: {ds.icon}")
            print(f"Action: {ds.action}")
            print(f"Layer: {ds.layer}")
            print(f"Created At: {ds.created_at}")
            print(f"Updated At: {ds.updated_at}")
            print("-" * 80)
    
except Exception as e:
    print(f"Error querying database: {e}")
    import traceback
    traceback.print_exc()

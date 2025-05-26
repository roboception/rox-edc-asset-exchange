import sys
import os

# Add project root to sys.path to allow for absolute-like imports from subdirectories
# if __init__.py files are present in them.
# This assumes test_both.py is in the project root.
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Updated imports to use __init__.py entrypoints
from provider import run_provider_main
from consumer import run_consumer_main

if __name__ == "__main__":

    print("\n--- Starting Test ---")
    asset_id_input = input("Define asset_id (e.g., test-asset-123): ")
    print(f"Running Current Provider and Current Consumer with asset_id: {asset_id_input}")
    
    # Updated function calls with correct parameter names and env file paths
    run_provider_main(asset_id=asset_id_input, env_file="provider/provider.env")
    run_consumer_main(asset_id_param=asset_id_input, env_file_param="consumer/consumer.env")
    
    print("--- Test Finished ---")




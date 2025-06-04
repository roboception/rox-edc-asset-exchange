#!/usr/bin/env python3
import argparse
import os
import sys
import logging
import requests
import json
from dotenv import load_dotenv

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

class ProviderAssetCleaner:
    def __init__(self, base_url: str, api_key: str):
        if not base_url or not api_key:
            raise ValueError("BASE_URL and API_KEY must be provided.")
        self.base_url = base_url.rstrip('/')
        # All management API calls in this EDC seem to be prefixed with /data
        self.management_api_prefix = "/data" 
        self.api_key = api_key
        self.management_headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        # EDC Namespace, often needed for context in queries, default if not in env
        self.edc_namespace = os.getenv("EDC_NAMESPACE", "https://w3id.org/edc/v0.0.1/ns/")


    def _send_request(self, method: str, endpoint_path: str, json_payload: dict = None, params: dict = None, operation_name: str = "Operation"):
        # Construct full URL with management_api_prefix and specific endpoint_path
        url = f"{self.base_url}{self.management_api_prefix}{endpoint_path}"
        logger.debug(f"{operation_name} - Method: {method}, URL: {url}, Payload: {json.dumps(json_payload) if json_payload else 'N/A'}")
        try:
            response = requests.request(method, url, headers=self.management_headers, json=json_payload, params=params)
            logger.info(f"{operation_name} - Status: {response.status_code}")
            
            response_dict = {
                "status_code": response.status_code,
                "content": response.text 
            }

            if 200 <= response.status_code < 300:
                if not response.content: 
                    response_dict["status"] = "success_no_content"
                    response_dict["data"] = None 
                else:
                    try:
                        response_dict["data"] = response.json()
                        response_dict["status"] = "success_json"
                    except ValueError:
                        logger.warning(f"{operation_name} - Response was not JSON despite success status. Content: {response.text[:200]}")
                        response_dict["status"] = "success_non_json"
                        # "data" will not be set, but "content" has the raw text
                # For all success cases, return the populated dict
                return response_dict
            else: # HTTP error status codes (300+)
                response_dict["status"] = "failed"
                try:
                    error_json = response.json()
                    # Log the full error internally here, as it's the first point of contact
                    logger.error(f"{operation_name} - HTTP Error. Status: {response.status_code}, Parsed Error JSON:\n{json.dumps(error_json, indent=2)}")
                    response_dict["error"] = error_json 
                except ValueError:
                    # Log the full error internally here
                    logger.error(f"{operation_name} - HTTP Error. Status: {response.status_code}, Raw Error Response: {response.text[:500]}")
                    response_dict["error"] = response.text[:500] 
                return response_dict # Return the structured error dictionary

        except requests.exceptions.RequestException as e:
            logger.error(f"{operation_name} - Request Exception: {e}")
            # Ensure a consistent dictionary structure for exceptions too
            return {"status": "exception", "status_code": None, "error": str(e), "content": str(e)}

    def list_assets(self):
        """Lists all assets using provider's management API, trying /v3/ endpoints first, then /v2/ as fallback."""
        
        # Primary attempt: GET to /v3/assets
        primary_endpoint_path = "/v3/assets" 
        operation_name_primary = "List Assets (GET /v3/assets)"
        logger.info(f"Attempting to list assets: {operation_name_primary} from {self.base_url}{self.management_api_prefix}{primary_endpoint_path}")
        response_dict = self._send_request("GET", primary_endpoint_path, params={"limit": 500}, operation_name=operation_name_primary)
        
        actual_asset_list = None
        if response_dict and response_dict.get("status") in ["success_json", "success_non_json"] and isinstance(response_dict.get("data"), list):
            actual_asset_list = response_dict.get("data")
        elif response_dict and response_dict.get("status_code") == 200 and isinstance(response_dict.get("content"), str): # Non-json success with string content
            try:
                actual_asset_list = json.loads(response_dict.get("content"))
                if not isinstance(actual_asset_list, list):
                    actual_asset_list = None # ensure it's a list
            except json.JSONDecodeError:
                logger.warning(f"{operation_name_primary} - Content was not valid JSON despite 200 status and non-empty content.")
                actual_asset_list = None

        if actual_asset_list is not None: # Check if we got a list of assets
            assets = []
            for asset_data in actual_asset_list:
                asset_id = asset_data.get('@id')
                if asset_id:
                    asset_name = asset_data.get('name', asset_data.get('id', asset_id))
                    properties = asset_data.get('properties')
                    if isinstance(properties, dict):
                        name_candidates = ['asset:prop:name', 'name', 'id', self.edc_namespace + 'name', self.edc_namespace + 'id']
                        name_candidates.extend([key for key in properties.keys() if 'name' in key.lower() or 'id' in key.lower()])
                        for cand_key in name_candidates:
                            if properties.get(cand_key):
                                asset_name = properties.get(cand_key)
                                break
                    elif isinstance(asset_data.get('asset:properties'), dict):
                        properties = asset_data.get('asset:properties')
                        name_candidates = ['asset:prop:name', 'name', 'id', 'dct:title', self.edc_namespace + 'name', self.edc_namespace + 'id']
                        for cand_key in name_candidates:
                            if properties.get(cand_key):
                                asset_name = properties.get(cand_key)
                                break
                    assets.append({'@id': asset_id, 'name': asset_name})
            
            logger.info(f"Found {len(assets)} assets via {operation_name_primary}.")
            return assets
        elif response_dict and response_dict.get("status") == "failed":
             logger.warning(f"Error listing assets with {operation_name_primary}: {response_dict.get('error')}. Trying next method.")
        else:
            logger.warning(f"Failed to list assets with {operation_name_primary} or unexpected response format. Response: {str(response_dict)[:300]}. Trying next method.")

        # Second attempt: POST to /v3/assets/request with a QuerySpec
        secondary_endpoint_path = "/v3/assets/request" 
        payload_v3_request = {
            "@context": {"@vocab": self.edc_namespace},
            "@type": "QuerySpec",
            "limit": 500
        }
        operation_name_secondary = "List Assets (POST /v3/assets/request)"
        logger.info(f"Attempting to list assets: {operation_name_secondary} from {self.base_url}{self.management_api_prefix}{secondary_endpoint_path}")
        response_dict_v3_post = self._send_request("POST", secondary_endpoint_path, json_payload=payload_v3_request, operation_name=operation_name_secondary)
        
        actual_asset_list_v3_post = None
        if response_dict_v3_post and response_dict_v3_post.get("status") == "success_json" and isinstance(response_dict_v3_post.get("data"), list):
            actual_asset_list_v3_post = response_dict_v3_post.get("data")

        if actual_asset_list_v3_post is not None:
            assets = []
            for asset_data in actual_asset_list_v3_post:
                asset_id = asset_data.get('@id')
                if asset_id:
                    asset_name = asset_data.get('name', asset_data.get('id', asset_id))
                    properties = asset_data.get('properties', asset_data.get('asset:properties'))
                    if isinstance(properties, dict):
                        name_candidates = ['asset:prop:name', 'name', 'id', 'dct:title', self.edc_namespace + 'name', self.edc_namespace + 'id']
                        for cand_key in name_candidates:
                            if properties.get(cand_key):
                                asset_name = properties.get(cand_key)
                                break
                    assets.append({'@id': asset_id, 'name': asset_name})
            logger.info(f"Found {len(assets)} assets via {operation_name_secondary}.")
            return assets
        elif response_dict_v3_post and response_dict_v3_post.get("status") == "failed":
            logger.warning(f"Error listing assets with {operation_name_secondary}: {response_dict_v3_post.get('error')}. Trying /v2/ fallbacks.")
        else:
            logger.warning(f"Failed to list assets with {operation_name_secondary} or unexpected response format. Response: {str(response_dict_v3_post)[:300]}. Trying /v2/ fallbacks.")

        # Fallback attempt 1: POST to /v2/assets/request with a QuerySpec
        fallback_v2_post_path = "/v2/assets/request" 
        payload_v2_request = {
            "@context": {"@vocab": self.edc_namespace},
            "@type": "QuerySpec",
            "limit": 500
        }
        operation_name_fallback_v2_post = "List Assets (POST /v2/assets/request)"
        logger.info(f"Attempting to list assets: {operation_name_fallback_v2_post} from {self.base_url}{self.management_api_prefix}{fallback_v2_post_path}")
        response_dict_v2_post = self._send_request("POST", fallback_v2_post_path, json_payload=payload_v2_request, operation_name=operation_name_fallback_v2_post)
        
        actual_asset_list_v2_post = None
        if response_dict_v2_post and response_dict_v2_post.get("status") == "success_json" and isinstance(response_dict_v2_post.get("data"), list):
            actual_asset_list_v2_post = response_dict_v2_post.get("data")

        if actual_asset_list_v2_post is not None:
            assets = [{'@id': asset.get('@id'), 'name': asset.get('properties',{}).get('asset:prop:name', asset.get('@id'))} for asset in actual_asset_list_v2_post if asset.get('@id')]
            logger.info(f"Found {len(assets)} assets via {operation_name_fallback_v2_post}.")
            return assets
        elif response_dict_v2_post and response_dict_v2_post.get("status") == "failed":
             logger.warning(f"Error listing assets with {operation_name_fallback_v2_post}: {response_dict_v2_post.get('error')}. Trying next method.")
        else:
            logger.warning(f"Failed to list assets with {operation_name_fallback_v2_post} or unexpected response format. Response: {str(response_dict_v2_post)[:300]}. Trying next method.")

        # Fallback attempt 2: GET to /v2/assets
        fallback_v2_get_path = "/v2/assets" 
        operation_name_fallback_v2_get = "List Assets (GET /v2/assets)"
        logger.info(f"Trying fallback: {operation_name_fallback_v2_get} from {self.base_url}{self.management_api_prefix}{fallback_v2_get_path}")
        response_dict_v2_get = self._send_request("GET", fallback_v2_get_path, params={"limit": 500}, operation_name=operation_name_fallback_v2_get)
        
        actual_asset_list_v2_get = None
        if response_dict_v2_get and response_dict_v2_get.get("status") == "success_json" and isinstance(response_dict_v2_get.get("data"), list):
            actual_asset_list_v2_get = response_dict_v2_get.get("data")
        
        if actual_asset_list_v2_get is not None:
            assets = [{'@id': asset.get('@id'), 'name': asset.get('properties',{}).get('asset:prop:name', asset.get('@id'))} for asset in actual_asset_list_v2_get if asset.get('@id')]
            logger.info(f"Found {len(assets)} assets via {operation_name_fallback_v2_get}.")
            return assets
        
        logger.error("Could not retrieve assets with any attempted method (/v3/assets GET, /v3/assets/request POST, /v2/assets/request POST, /v2/assets GET). Please check EDC logs for supported endpoints.")
        return []

    def delete_asset(self, asset_id: str):
        """Deletes an asset by its ID using /v3/assets/{asset_id}."""
        endpoint_path = f"/v3/assets/{asset_id}" # Path relative to management_api_prefix
        operation_name = f"Delete Asset {asset_id}"
        logger.info(f"Attempting to delete asset: {asset_id} via {self.base_url}{self.management_api_prefix}{endpoint_path}")
        
        response_data = self._send_request("DELETE", endpoint_path, operation_name=operation_name)

        if not response_data or not isinstance(response_data, dict):
            logger.error(f"Failed to delete asset '{asset_id}'. Invalid response from _send_request: {str(response_data)[:1000]}")
            return False

        status_code = response_data.get("status_code")
        response_status = response_data.get("status") # e.g., "success_json", "failed", "exception"
        error_details = response_data.get("error") 
        
        is_success = False
        if response_status == "success_no_content":
            is_success = True
        elif response_status == "success_json" and (status_code == 200 or status_code == 204):
            is_success = True
        elif response_status == "success_non_json" and (status_code == 200 or status_code == 204):
            is_success = True

        if is_success:
            logger.info(f"Asset '{asset_id}' deleted successfully (Status: {status_code}).")
            return True
        
        if status_code == 409:
            message = "Conflict detected (409)."
            if error_details:
                if isinstance(error_details, list) and len(error_details) > 0 and isinstance(error_details[0], dict):
                    message = error_details[0].get("message", str(error_details))
                elif isinstance(error_details, dict):
                    message = error_details.get("message", str(error_details))
                else:
                    message = str(error_details) 
            logger.warning(f"Asset '{asset_id}' cannot be deleted. Status: 409. EDC Message: {message}")
            return False
        
        if status_code is not None and status_code >= 300: # Covers 4xx and 5xx errors not specifically 409
            failure_reason = str(error_details if error_details else response_data.get("content", "Unknown error"))
            logger.error(f"Failed to delete asset '{asset_id}'. Status: {status_code}. Details: {failure_reason[:1000]}")
            return False
        
        # Fallback for other cases, e.g. status="exception" or unexpected structure
        logger.error(f"Failed to delete asset '{asset_id}'. Status: {status_code if status_code else 'N/A'}, Response Status: {response_status if response_status else 'N/A'}, Details: {str(error_details if error_details else response_data.get('content', 'No content'))[:1000]}")
        return False

    # --- Contract Definition Management --- 
    def list_contract_definitions(self):
        """Lists all contract definitions using /v2/contractdefinitions/request."""
        endpoint_path = "/v2/contractdefinitions/request"
        payload = {
            "@context": {"@vocab": self.edc_namespace},
            "@type": "QuerySpec",
            "limit": 500 
        }
        operation_name = "List Contract Definitions"
        logger.info(f"Attempting to list contract definitions from {self.base_url}{self.management_api_prefix}{endpoint_path}")
        response_dict = self._send_request("POST", endpoint_path, json_payload=payload, operation_name=operation_name)
        
        definitions = []
        actual_cd_list = None

        if response_dict and response_dict.get("status") == "success_json" and isinstance(response_dict.get("data"), list):
            actual_cd_list = response_dict.get("data")
        # Potentially handle success_non_json if CD list can ever be non-JSON (unlikely for POST /request)
        
        if actual_cd_list is not None:
            for cd_data_item in actual_cd_list: 
                if not isinstance(cd_data_item, dict): 
                    logger.warning(f"Skipping non-dictionary item in contract definition list: {str(cd_data_item)[:100]}")
                    continue
                cd_id = cd_data_item.get('@id')
                if not cd_id:
                    logger.warning(f"Skipping contract definition item with no '@id': {str(cd_data_item)[:100]}")
                    continue

                asset_selector_value = None
                assets_selector_raw = cd_data_item.get('assetsSelector')
                criteria_to_check = []

                if isinstance(assets_selector_raw, dict): 
                    criteria_to_check.append(assets_selector_raw)
                elif isinstance(assets_selector_raw, list): 
                    criteria_to_check = assets_selector_raw
                elif 'criterion' in cd_data_item:
                    criterion_fallback = cd_data_item.get('criterion')
                    if isinstance(criterion_fallback, dict):
                        criteria_to_check.append(criterion_fallback)
                    elif isinstance(criterion_fallback, list):
                        criteria_to_check.extend(criterion_fallback)
                
                for criterion in criteria_to_check:
                    if isinstance(criterion, dict):
                        op_left = criterion.get('operandLeft')
                        op_operator = criterion.get('operator')
                        is_edc_id_operand = (op_left == (self.edc_namespace + 'id') or 
                                             op_left == 'https://w3id.org/edc/v0.0.1/ns/id')
                        is_equals_operator = (op_operator == '=')
                        
                        if is_edc_id_operand and is_equals_operator:
                            asset_selector_value = criterion.get('operandRight')
                            if asset_selector_value: 
                                break 
                
                definitions.append({
                    '@id': cd_id,
                    'accessPolicyId': cd_data_item.get('accessPolicyId'),
                    'contractPolicyId': cd_data_item.get('contractPolicyId'),
                    'assetsSelectorTarget': asset_selector_value
                })
            logger.info(f"Found and processed {len(definitions)} contract definitions.")
            # Return here, as we successfully processed the list
            return definitions 
        
        # Handle error cases or unexpected format after attempting to get actual_cd_list
        if response_dict and response_dict.get("status") == "failed":
             logger.error(f"Error listing contract definitions (server reported error): {response_dict.get('error')}")
        else:
            # This covers cases like status != success_json, or actual_cd_list was None for other reasons
            logger.warning(f"Failed to list contract definitions or unexpected response format. Full Response: {str(response_dict)[:500]}")
        return [] # Return empty list if not successful

    def get_raw_contract_definition(self, cd_id: str):
        """Fetches the raw JSON for a single contract definition by its ID."""
        endpoint_path = f"/v2/contractdefinitions/{cd_id}"
        operation_name = f"Get Raw Contract Definition {cd_id}"
        logger.info(f"Attempting to get raw contract definition: {cd_id} from {self.base_url}{self.management_api_prefix}{endpoint_path}")
        # _send_request returns the parsed JSON directly on success, or an error dict
        response_data = self._send_request("GET", endpoint_path, operation_name=operation_name)
        
        if response_data and not response_data.get("error") and response_data.get("status_code") is None: # Success and has content
             # if _send_request returns data directly without status_code in a wrapper for GET success
            return response_data 
        elif response_data and response_data.get("status_code") and response_data.get("status_code") >= 200 and response_data.get("status_code") < 300:
            return response_data # It might be wrapped if _send_request changes, but usually direct for GET
        else:
            logger.error(f"Failed to get raw contract definition '{cd_id}'. Response: {response_data}")
            return None

    def delete_contract_definition(self, cd_id: str):
        """Deletes a contract definition by its ID using /v2/contractdefinitions/{id}."""
        endpoint_path = f"/v2/contractdefinitions/{cd_id}"
        operation_name = f"Delete Contract Definition {cd_id}"
        logger.info(f"Attempting to delete contract definition: {cd_id} via {self.base_url}{self.management_api_prefix}{endpoint_path}")
        response_data = self._send_request("DELETE", endpoint_path, operation_name=operation_name)

        if not response_data:
            logger.error(f"Failed to delete contract definition '{cd_id}'. No response from server.")
            return False
        
        status_code = response_data.get("status_code")
        if status_code == 200 or status_code == 204 or response_data.get("status") == "success_no_content":
            logger.info(f"Contract definition '{cd_id}' deleted successfully (Status: {status_code if status_code else '204 via status'}).")
            return True
        else:
            error_payload = response_data.get("error", response_data.get("content", "Unknown error"))
            logger.error(f"Failed to delete contract definition '{cd_id}'. Status: {status_code if status_code else 'N/A'}, Details: {str(error_payload)[:1000]}")
            return False

    # --- Contract Agreement Management ---
    def list_contract_agreements(self):
        """Lists all contract agreements using /v2/contractagreements/request."""
        endpoint_path = "/v2/contractagreements/request" 
        payload = {
            "@context": {"@vocab": self.edc_namespace},
            "@type": "QuerySpec",
            "limit": 500 
        }
        operation_name = "List Contract Agreements"
        logger.info(f"Attempting to list contract agreements from {self.base_url}{self.management_api_prefix}{endpoint_path}")
        response_dict = self._send_request("POST", endpoint_path, json_payload=payload, operation_name=operation_name)
        
        agreements = []
        actual_ca_list = None

        if response_dict and response_dict.get("status") == "success_json" and isinstance(response_dict.get("data"), list):
            actual_ca_list = response_dict.get("data")
        
        if actual_ca_list is not None:
            for ca_data_item in actual_ca_list:
                if not isinstance(ca_data_item, dict):
                    logger.warning(f"Skipping non-dictionary item in contract agreement list: {str(ca_data_item)[:100]}")
                    continue
                ca_id = ca_data_item.get('@id')
                if not ca_id:
                    logger.warning(f"Skipping contract agreement item with no '@id': {str(ca_data_item)[:100]}")
                    continue
                
                # Attempt to extract assetId. Common EDC field name is 'assetId'.
                # Sometimes it could be nested or under policy.target.
                target_asset_id = ca_data_item.get('assetId') 
                if not target_asset_id:
                    # Check within a nested 'asset' object if 'assetId' is not top-level
                    asset_obj = ca_data_item.get('asset')
                    if isinstance(asset_obj, dict):
                        target_asset_id = asset_obj.get('@id')
                if not target_asset_id:
                    # Check within the policy object, typically 'target' field
                    policy = ca_data_item.get('policy', {})
                    if isinstance(policy, dict):
                        target_asset_id = policy.get('target')
                        # Deeper check if target itself is an object with @id (less common for CA policy target)
                        if isinstance(target_asset_id, dict):
                            target_asset_id = target_asset_id.get('@id')

                agreements.append({
                    '@id': ca_id,
                    'assetId': target_asset_id, 
                    'providerId': ca_data_item.get('providerId'),
                    'consumerId': ca_data_item.get('consumerId')
                    # Add other fields like contractStartDate, contractEndDate if useful for debugging later
                })
            logger.info(f"Found and processed {len(agreements)} contract agreements.")
            return agreements
        
        if response_dict and response_dict.get("status") == "failed":
             logger.error(f"Error listing contract agreements (server reported error): {response_dict.get('error')}")
        else:
            logger.warning(f"Failed to list contract agreements or unexpected response format. Full Response: {str(response_dict)[:500]}")
        return []

    def delete_contract_agreement(self, agreement_id: str):
        """Deletes a contract agreement by its ID using /v2/contractagreements/{id}."""
        endpoint_path = f"/v2/contractagreements/{agreement_id}"
        operation_name = f"Delete Contract Agreement {agreement_id}"
        logger.info(f"Attempting to delete contract agreement: {agreement_id} via {self.base_url}{self.management_api_prefix}{endpoint_path}")
        response_data = self._send_request("DELETE", endpoint_path, operation_name=operation_name)

        if not response_data or not isinstance(response_data, dict):
            logger.error(f"Failed to delete contract agreement '{agreement_id}'. Invalid response from _send_request: {str(response_data)[:1000]}")
            return False

        status_code = response_data.get("status_code")
        response_status = response_data.get("status")
        error_details = response_data.get("error")

        is_success = False
        if response_status == "success_no_content": 
            is_success = True
        elif response_status == "success_json" and (status_code == 200 or status_code == 204):
            is_success = True 
        elif response_status == "success_non_json" and (status_code == 200 or status_code == 204):
            is_success = True

        if is_success:
            logger.info(f"Contract agreement '{agreement_id}' deleted successfully (Status: {status_code}).")
            return True
        
        # Specific handling for 405 Method Not Allowed
        if status_code == 405:
            logger.error(f"Failed to delete contract agreement '{agreement_id}'. Status: 405 (Method Not Allowed). This EDC may not support direct deletion of agreements via this endpoint.")
            return False

        failure_reason = str(error_details if error_details else response_data.get("content", "Unknown error"))
        logger.error(f"Failed to delete contract agreement '{agreement_id}'. Status: {status_code if status_code else 'N/A'}, Details: {failure_reason[:1000]}")
        return False

def get_user_selection(assets: list):
    if not assets:
        logger.info("No assets found to select for deletion.")
        return []

    print("\nAvailable assets for deletion:")
    for i, asset in enumerate(assets):
        print(f"  {i+1}. ID: {asset.get('@id')} (Name: {asset.get('name', 'N/A')})")
    
    selected_indices = set()
    while True:
        try:
            choice_str = input("Select assets to delete by number (e.g., 1,3,5), 'A' for All, 'N' for None, then press Enter: ").strip().upper()
            if not choice_str: # User pressed Enter
                if not selected_indices:
                    print("No assets selected. Type 'N' if you want to select none, or provide numbers.")
                    continue
                break

            if choice_str == 'A':
                selected_indices = set(range(len(assets)))
                print(f"All {len(assets)} assets selected.")
                break 
            if choice_str == 'N':
                selected_indices = set()
                print("No assets selected.")
                break

            # Clear previous partial selections if new input is given
            current_selection_this_รอบ = set()
            parts = choice_str.split(',')
            valid_choice_made = False
            for part in parts:
                part = part.strip()
                if not part: continue
                if part.upper() == 'A':
                    current_selection_this_รอบ.update(range(len(assets)))
                    valid_choice_made = True
                    continue
                if part.upper() == 'N':
                    current_selection_this_รอบ.clear() # N overrides others in this specific input
                    valid_choice_made = True
                    break 
                
                choice_num = int(part) -1
                if 0 <= choice_num < len(assets):
                    current_selection_this_รอบ.add(choice_num)
                    valid_choice_made = True
                else:
                    print(f"Invalid selection: '{part}'. Number out of range.")
            
            if valid_choice_made :
                 # Update main selection: user can toggle by re-entering
                 for idx_to_toggle in current_selection_this_รอบ:
                     if idx_to_toggle in selected_indices:
                         selected_indices.remove(idx_to_toggle)
                     else:
                         selected_indices.add(idx_to_toggle)

            if selected_indices:
                print("Currently selected for deletion:")
                for i in sorted(list(selected_indices)):
                     print(f"  - {assets[i].get('@id')}")
            else:
                print("No assets currently selected.")

        except ValueError:
            print("Invalid input. Please enter numbers, 'A', or 'N'.")
        except KeyboardInterrupt:
            print("\nSelection cancelled by user.")
            return []
            
    return [assets[i] for i in selected_indices]


def main():
    parser = argparse.ArgumentParser(description="Provider-side asset cleanup utility.")
    parser.add_argument(
        "-e",
        "--env",
        default="provider/provider.env",
        help="Path to the environment file (default: provider/provider.env)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Automatically confirm deletions without prompting.",
    )
    args = parser.parse_args()

    env_full_path = os.path.abspath(args.env)
    if not os.path.exists(env_full_path):
        logger.error(f"Environment file not found: {env_full_path}")
        sys.exit(1)
    
    logger.info(f"Loading environment from: {env_full_path}")
    load_dotenv(env_full_path, override=True)

    # These should be set in the .env file loaded
    base_url = os.getenv("BASE_URL")
    api_key = os.getenv("API_KEY")
    
    if not base_url:
        logger.error("CRITICAL: BASE_URL environment variable not set in the .env file.")
        sys.exit(1)
    if not api_key:
        logger.error("CRITICAL: API_KEY environment variable not set in the .env file.")
        sys.exit(1)

    cleaner = ProviderAssetCleaner(base_url=base_url, api_key=api_key)
    
    assets_to_list = cleaner.list_assets()
    if not assets_to_list:
        logger.info("No assets found on the provider to manage.")
        return

    selected_assets = get_user_selection(assets_to_list)

    if not selected_assets:
        logger.info("No assets were selected for deletion.")
        return

    logger.info("\nThe following assets are selected for DELETION:")
    for asset in selected_assets:
        logger.info(f"  - ID: {asset.get('@id')} (Name: {asset.get('name')})")
    
    if not args.yes:
        confirm = input("\nAre you sure you want to delete these assets (and their directly related contract definitions AND contract agreements)? This action CANNOT be undone. (yes/no): ").strip().lower()
        if confirm != 'yes':
            logger.info("Deletion cancelled by user.")
            return

    logger.info("\n--- Fetching all contract definitions to check dependencies ---")
    all_contract_definitions = cleaner.list_contract_definitions()

    # ---- DEBUG: Print first CD (processed and raw) ----
    if all_contract_definitions:
        logger.info("\n--- DEBUG: First Contract Definition (Processed) ---")
        logger.info(f"CD 1 (Processed): {json.dumps(all_contract_definitions[0], indent=2)}")
        first_cd_id_debug = all_contract_definitions[0].get('@id')
        if first_cd_id_debug:
            logger.info("\n--- DEBUG: RAW structure of first Contract Definition ---")
            raw_cd_data_debug = cleaner.get_raw_contract_definition(first_cd_id_debug)
            if raw_cd_data_debug:
                logger.info(f"CD 1 (RAW from GET {first_cd_id_debug}): {json.dumps(raw_cd_data_debug, indent=2)}")
    # ---- END DEBUG ----

    logger.info("\n--- Fetching all contract agreements to check dependencies ---")
    all_contract_agreements = cleaner.list_contract_agreements()

    # ---- DEBUG: Print first CA if available ----
    if all_contract_agreements:
        logger.info("\n--- DEBUG: First Contract Agreement (Processed) ---")
        logger.info(f"CA 1 (Processed): {json.dumps(all_contract_agreements[0], indent=2)}")
    else:
        logger.info("\n--- DEBUG: No contract agreements found or processed ---")
    # ---- END DEBUG ----

    deleted_assets_count = 0
    failed_assets_count = 0
    deleted_cds_count = 0
    failed_cds_count = 0
    deleted_cas_count = 0 # Contract Agreements deleted
    failed_cas_count = 0  # Contract Agreements failed to delete

    for asset in selected_assets:
        asset_id = asset.get('@id')
        logger.info(f"\n--- Processing asset for deletion: {asset_id} ---")

        # Step 1: Attempt to delete dependent contract definitions for this asset
        logger.info(f"Checking for contract definitions targeting asset: {asset_id}")
        found_related_cd = False
        for cd in all_contract_definitions:
            if cd.get('assetsSelectorTarget') == asset_id:
                found_related_cd = True
                logger.info(f"Found contract definition '{cd.get('@id')}' targeting asset '{asset_id}'. Attempting to delete it.")
                if cleaner.delete_contract_definition(cd.get('@id')):
                    deleted_cds_count += 1
                else:
                    failed_cds_count += 1
                    logger.warning(f"Failed to delete contract definition '{cd.get('@id')}' for asset '{asset_id}'. Asset deletion might still be blocked.")
        if not found_related_cd:
            logger.info(f"No specific contract definitions found directly targeting asset '{asset_id}'.")

        # Step 2: Attempt to delete dependent contract agreements for this asset
        logger.info(f"Checking for contract agreements related to asset: {asset_id}")
        found_related_ca = False
        for ca in all_contract_agreements:
            # The assetId in the agreement should match the asset_id we are trying to delete.
            # Note: list_contract_agreements tries to populate ca.get('assetId') correctly.
            if ca.get('assetId') == asset_id:
                found_related_ca = True
                logger.info(f"Found contract agreement '{ca.get('@id')}' for asset '{asset_id}'. Attempting to delete it.")
                if cleaner.delete_contract_agreement(ca.get('@id')):
                    deleted_cas_count += 1
                else:
                    failed_cas_count += 1
                    # The delete_contract_agreement method now logs specifics, including 405
                    logger.warning(f"Failed to delete contract agreement '{ca.get('@id')}' for asset '{asset_id}'. Asset deletion will likely be blocked if this CA was the cause.")
        if not found_related_ca:
            logger.info(f"No contract agreements found directly referencing asset '{asset_id}'.")

        # Step 3: Attempt to delete the asset itself
        logger.info(f"Attempting to delete asset: {asset_id} (after CD and CA cleanup attempts)")
        if cleaner.delete_asset(asset_id):
            deleted_assets_count += 1
        else:
            failed_assets_count += 1
    
    logger.info(f"\n--- Deletion Summary ---")
    logger.info(f"Successfully deleted: {deleted_assets_count} asset(s)")
    if failed_assets_count > 0:
        logger.warning(f"Failed to delete: {failed_assets_count} asset(s)")
    logger.info(f"Successfully deleted: {deleted_cds_count} contract definition(s)")
    if failed_cds_count > 0:
        logger.warning(f"Failed to delete: {failed_cds_count} contract definition(s)")
    logger.info(f"Successfully deleted: {deleted_cas_count} contract agreement(s)")
    if failed_cas_count > 0:
        logger.warning(f"Failed to delete: {failed_cas_count} contract agreement(s)")
    
    logger.info("Asset cleanup process finished.")
    logger.warning("Note: This script attempts to delete assets, their targeting contract definitions, and related contract agreements.")
    logger.warning("Assets referenced by contract agreements that could not be deleted (e.g., due to EDC restrictions like 405 Method Not Allowed on agreement deletion) will remain on the provider.")

if __name__ == "__main__":
    main() 
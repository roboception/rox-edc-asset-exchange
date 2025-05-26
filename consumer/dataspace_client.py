import requests
import os
import json
import time
import logging
from .config import settings  # Import global settings

# Default values, though many will come from settings now
DEFAULT_HEADERS = {"Content-Type": "application/json"}


class DataspaceClient:
    """
    Client for interacting with a provider's EDC Management API and DSP endpoints.

    Handles consumer-side Dataspace operations: catalog requests, contract negotiations (EDR),
    EDR polling, data address retrieval, and data download.
    Configuration is sourced from the global `settings` object.
    """

    def __init__(self):
        """
        Initializes the client with settings, sets up logging, and prepares artifact download directory.
        Raises ValueError if essential configurations (BASE_URL, API_KEY, PROVIDER_BPN) are missing.
        """
        self.logger = logging.getLogger(__name__)

        # Validate essential settings
        if not settings.BASE_URL or not settings.API_KEY:
            raise ValueError(
                "DataspaceClient: Provider's BASE_URL or API_KEY not configured."
            )
        if not settings.PROVIDER_BPN:
            raise ValueError(
                "DataspaceClient: PROVIDER_BPN (Target Provider BPN) not set in settings."
            )

        # Provider's Management API details
        self.base_url = settings.BASE_URL
        self.api_key = settings.API_KEY
        self.provider_bpn = settings.PROVIDER_BPN

        # EDC and logging settings
        self.edc_namespace = settings.EDC_NAMESPACE
        self.print_response_flag = settings.PRINT_RESPONSE
        self.edr_polling_timeout_seconds = settings.EDR_POLLING_TIMEOUT_SECONDS
        self.response_print_limit = settings.RESPONSE_PRINT_LIMIT
        self.print_first_json_element_only = settings.PRINT_FIRST_JSON_ELEMENT_ONLY

        # Provider's DSP endpoint, derived from their management API base URL
        # Assumes a common pattern where DSP is at '/api/v1/dsp' relative to management API.
        self.provider_protocol_url = self.base_url.rstrip("/") + "/api/v1/dsp"

        self.last_response_status_code = (
            None  # Stores status of the most recent HTTP request
        )
        self.polling_interval = 1  # seconds, for EDR polling

        # Ensure local directory for downloaded artifacts exists
        os.makedirs(settings.ARTIFACT_DOWNLOAD_PATH, exist_ok=True)
        self.logger.info(
            f"Artifact download path ensured: {settings.ARTIFACT_DOWNLOAD_PATH}"
        )

    def _get_management_headers(self) -> dict:
        """
        Constructs headers required for authenticating with the Provider's Management API.
        Includes the API key if provided in settings.
        """
        headers = DEFAULT_HEADERS.copy()
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

    def _format_json_for_logging(self, json_data: any) -> str:
        """
        Formats JSON data for logging, applying configured truncation and list handling.

        Args:
            json_data: The JSON data (as a Python dict or list) to format.

        Returns:
            A string representation of the JSON data, formatted for logging.
        """
        # Case 1: Print only the first element of a non-empty list
        if (
            self.print_first_json_element_only
            and isinstance(json_data, list)
            and len(json_data) > 0
        ):
            first_element_str = json.dumps(json_data[0], indent=2)
            # RESPONSE_PRINT_LIMIT is not applied here by design, to show one full item clearly.
            return (
                first_element_str
                + f"\n(... {len(json_data) -1} more list elements omitted)"
            )

        # Case 2: Handle empty list
        elif isinstance(json_data, list) and len(json_data) == 0:
            return "[]"

        # Case 3: Print the full JSON (dict, or list if print_first_json_element_only is False)
        # RESPONSE_PRINT_LIMIT applies here.
        else:
            try:
                full_json_str = json.dumps(json_data, indent=2)
                if len(full_json_str) > self.response_print_limit:
                    return (
                        full_json_str[: self.response_print_limit] + "... (truncated)"
                    )
                else:
                    return full_json_str
            except (
                TypeError
            ):  # Handle cases where json_data might not be directly serializable
                self.logger.warning(
                    f"Could not serialize data for logging: {type(json_data)}"
                )
                return (
                    str(json_data)[: self.response_print_limit] + "... (raw, truncated)"
                )

    def _send_request(
        self,
        method: str,
        url: str,
        headers: dict = None,
        json_payload: dict = None,
        params: dict = None,
        operation_name: str = "Generic Operation",
        stream: bool = False,
    ) -> dict | requests.Response | None:
        """
        Internal helper to send HTTP requests and handle responses.

        Args:
            method: HTTP method (e.g., "GET", "POST").
            url: The target URL.
            headers: Optional dictionary of request headers. Uses management headers if None.
            json_payload: Optional dictionary for JSON request body.
            params: Optional dictionary for URL query parameters.
            operation_name: A descriptive name for the operation, used in logs.
            stream: If True, returns the raw Response object for streaming.

        Returns:
            A dictionary with response data or error details,
            or a `requests.Response` object if `stream` is True and successful,
            or None if a critical request exception occurs.
        """
        payload_to_log = (
            self._format_json_for_logging(json_payload) if json_payload else "N/A"
        )
        self.logger.debug(
            f"{operation_name} - Request - Method: {method}, URL: {url}, Payload: {payload_to_log}, Params: {params}"
        )

        try:
            actual_headers = (
                headers if headers is not None else self._get_management_headers()
            )
            response = requests.request(
                method,
                url,
                headers=actual_headers,
                json=json_payload,
                params=params,
                stream=stream,
            )
            self.last_response_status_code = response.status_code
            self.logger.info(
                f"{operation_name} - Response Status: {response.status_code}"
            )

            # Detailed logging of response content based on flags
            if self.print_response_flag and not stream and response.content:
                try:
                    response_json = response.json()
                    log_output = self._format_json_for_logging(response_json)
                    self.logger.info(f"{operation_name} - Response JSON:\n{log_output}")
                except ValueError:  # Not JSON
                    # Use self.response_print_limit for non-JSON text response
                    self.logger.info(
                        f"{operation_name} - Response Text: {response.text[:self.response_print_limit]}"
                    )
            elif (
                not stream and response.content
            ):  # Log debug if print_response_flag is false
                self.logger.debug(
                    f"{operation_name} - Raw Response Text: {response.text[:self.response_print_limit]}"
                )

            # Handle response based on status code
            if 200 <= response.status_code < 300:
                if stream:
                    return response  # Return raw response for streaming
                if not response.content:  # Success but no content
                    return {
                        "status": "success_no_content",
                        "status_code": response.status_code,
                    }
                try:
                    return response.json()  # Attempt to parse JSON
                except ValueError:
                    self.logger.warning(
                        f"{operation_name} - Successful response was not JSON."
                    )
                    return {
                        "status": "success_non_json",
                        "content": response.text,
                        "status_code": response.status_code,
                    }
            else:  # Error handling
                error_text = response.text[
                    : self.response_print_limit
                ]  # Truncate error text
                try:
                    error_json = response.json()
                    log_output = self._format_json_for_logging(error_json)
                    self.logger.error(
                        f"{operation_name} - Failed. Status: {response.status_code}, Parsed Error JSON:\n{log_output}"
                    )
                    return {"error": error_json, "status_code": response.status_code}
                except ValueError:  # Error response was not JSON
                    self.logger.error(
                        f"{operation_name} - Failed. Status: {response.status_code}, Raw Error Response: {error_text}"
                    )
                    return {"error": error_text, "status_code": response.status_code}

        except requests.exceptions.RequestException as e:
            self.logger.error(f"{operation_name} - Request Exception: {e}")
            return {
                "error": str(e),
                "status_code": None,
            }  # Return status_code as None for request exceptions
        except (
            Exception
        ) as e:  # Catch any other unexpected errors during request sending
            self.logger.error(
                f"{operation_name} - Unexpected error during request: {e}"
            )
            return {"error": f"Unexpected error: {str(e)}", "status_code": None}

    def request_catalog(self, asset_id_filter: str = None) -> dict | list | None:
        """
        Requests the asset catalog from the provider's Management API.

        Can optionally filter for a specific asset ID. Handles cases where the
        provider returns a single dataset as a dict or multiple as a list.

        Args:
            asset_id_filter: Optional asset ID to filter the catalog.

        Returns:
            A dictionary representing the single matching dataset if filtered and found,
            a list of dataset dictionaries if no filter is applied or multiple found (though
            current EDC behavior with ID filter usually returns one or none),
            or None if an error occurs or the asset is not found.
        """
        operation_name = (
            f"Catalog Request (Asset Filter: {asset_id_filter or 'All Assets'})"
        )
        self.logger.info(f"{operation_name} - Target Provider: {self.base_url}")

        request_url = f"{self.base_url.rstrip('/')}/data/v2/catalog/request"

        # Construct the querySpec for the catalog request
        query_spec = {
            "offset": 0,
            "limit": settings.CATALOG_REQUEST_LIMIT,
        }  # Use a setting for limit
        if asset_id_filter:
            query_spec["filterExpression"] = [
                {
                    "operandLeft": f"{self.edc_namespace}id",  # Use configured EDC namespace
                    "operator": "=",
                    "operandRight": asset_id_filter,
                }
            ]

        payload = {
            "@context": {},  # Minimal context for catalog request
            "protocol": "dataspace-protocol-http",
            "counterPartyAddress": self.provider_protocol_url,  # Provider's DSP endpoint
            "counterPartyId": self.provider_bpn,  # Provider's BPN
            "querySpec": query_spec,
        }

        response_data = self._send_request(
            "POST", request_url, json_payload=payload, operation_name=operation_name
        )

        if not response_data or response_data.get("error"):
            self.logger.error(
                f"{operation_name} - Failed or error in response: {response_data}"
            )
            return None

        # EDC catalog responses can have 'dcat:dataset' or 'edc:datasets'
        datasets_from_response = response_data.get(
            "dcat:dataset", response_data.get("edc:datasets")
        )

        if not datasets_from_response:
            self.logger.warning(
                f"{operation_name} - No datasets found in catalog response (key 'dcat:dataset' or 'edc:datasets' was empty/missing)."
            )
            return None

        # Handle different structures of datasets_from_response based on filter
        if asset_id_filter:
            # Expecting a single dataset (dict) or a list which should contain the one.
            if isinstance(datasets_from_response, dict):
                if datasets_from_response.get("@id") == asset_id_filter:
                    self.logger.info(
                        f"{operation_name} - Asset '{asset_id_filter}' found directly as single object."
                    )
                    return datasets_from_response
                else:
                    self.logger.warning(
                        f"{operation_name} - Asset '{asset_id_filter}' not found; single dataset returned has ID '{datasets_from_response.get('@id')}'."
                    )
                    return None
            elif isinstance(datasets_from_response, list):
                self.logger.info(
                    f"{operation_name} - Received {len(datasets_from_response)} dataset(s) in list (with filter '{asset_id_filter}'). Searching..."
                )
                for ds_item in datasets_from_response:
                    if (
                        isinstance(ds_item, dict)
                        and ds_item.get("@id") == asset_id_filter
                    ):
                        self.logger.info(
                            f"{operation_name} - Asset '{asset_id_filter}' found in catalog list."
                        )
                        return ds_item
                self.logger.warning(
                    f"{operation_name} - Asset '{asset_id_filter}' not found in the list of datasets."
                )
                return None
            else:  # Unexpected structure
                self.logger.warning(
                    f"{operation_name} - Unexpected structure for filtered catalog response. Type: {type(datasets_from_response)}"
                )
                return None
        else:  # No filter applied, expecting all assets
            if isinstance(datasets_from_response, list):
                self.logger.info(
                    f"{operation_name} - Found {len(datasets_from_response)} dataset(s) in catalog list (no filter)."
                )
                return datasets_from_response
            elif isinstance(
                datasets_from_response, dict
            ):  # Single dataset returned without filter
                self.logger.info(
                    f"{operation_name} - Found 1 dataset as single object (no filter). Wrapping in list for consistency."
                )
                return [datasets_from_response]  # Ensure consistent return type
            else:  # Unexpected structure
                self.logger.warning(
                    f"{operation_name} - Unexpected structure for unfiltered catalog response. Type: {type(datasets_from_response)}"
                )
                return None

    def initiate_contract(
        self, asset_id: str, full_policy_object: dict
    ) -> tuple[str | None, dict | None]:
        """
        Initiates a contract negotiation (EDR) with the provider for a given asset and policy.

        This involves sending a ContractRequest to the provider's EDR endpoint.
        The policy object is augmented with required `odrl:target` and `odrl:assigner`.

        Args:
            asset_id: The ID of the asset for which to request a contract.
            full_policy_object: The complete policy object from the catalog associated with the asset.

        Returns:
            A tuple containing:
            - The EDR ID (negotiation ID) if initiation is successful, else None.
            - The full response from the EDR initiation if successful, else None.
        """
        operation_name = f"EDR Initiation (Asset: {asset_id}, Policy ID: {full_policy_object.get('@id', 'N/A')})"
        self.logger.info(operation_name)
        request_url = f"{self.base_url.rstrip('/')}/data/v2/edrs"  # EDC EDR endpoint

        # Prepare the policy to send: copy from catalog and augment/override key fields.
        # This aligns with observed requirements from EDC providers and Bruno examples.
        policy_to_send = full_policy_object.copy()
        policy_to_send["odrl:target"] = {"@id": asset_id}
        policy_to_send["odrl:assigner"] = {"@id": self.provider_bpn}
        if (
            "@type" not in policy_to_send
        ):  # Ensure policy @type is set, defaulting to "odrl:Offer"
            policy_to_send["@type"] = "odrl:Offer"
            self.logger.warning(
                f"{operation_name} - Policy from catalog (ID: {full_policy_object.get('@id', 'N/A')}) was missing '@type', defaulted to 'odrl:Offer'."
            )

        # Construct the ContractRequest payload
        payload = {
            "@context": {  # Standard EDC context for contract requests
                "odrl": "http://www.w3.org/ns/odrl/2/",
                "edc": self.edc_namespace,
                "cx-policy": "https://w3id.org/catenax/policy/",  # Adding common CX namespaces
                "tx": "https://w3id.org/tractusx/v0.0.1/ns/",
            },
            "@type": "ContractRequest",
            "counterPartyAddress": self.provider_protocol_url,  # Provider's DSP endpoint
            "protocol": "dataspace-protocol-http",
            "policy": policy_to_send,  # The augmented policy object
        }

        response_data = self._send_request(
            "POST", request_url, json_payload=payload, operation_name=operation_name
        )

        if (
            response_data
            and not response_data.get("error")
            and response_data.get("@id")
        ):
            edr_id = response_data["@id"]  # This is the negotiation ID
            self.logger.info(
                f"{operation_name} - EDR initiation successful. Negotiation ID: {edr_id}"
            )
            return edr_id, response_data  # Return ID and full negotiation details
        else:
            self.logger.error(
                f"{operation_name} - Failed to initiate EDR or missing ID in response: {response_data}"
            )
            return None, None

    def get_cached_edrs(
        self, asset_id_for_filter: str = None
    ) -> tuple[str | None, dict | None]:
        """
        Polls the provider's EDR cache to find a finalized EDR for a given asset.

        A finalized EDR is identified by the presence of a `transferProcessId`.
        Polling continues until an EDR is found or the timeout is reached.

        Args:
            asset_id_for_filter: The asset ID to filter EDRs for. If None, polls for any EDR
                                 from the configured provider (though typically used with an asset ID).

        Returns:
            A tuple containing:
            - The `transferProcessId` of the finalized EDR if found, else None.
            - The full EDR entry dictionary if found, else None.
        """
        operation_name = (
            f"EDR Cache Polling (Asset Filter: {asset_id_for_filter or 'Any'})"
        )
        self.logger.info(operation_name)
        request_url = (
            f"{self.base_url.rstrip('/')}/data/v2/edrs/request"  # EDR query endpoint
        )

        # Construct filter expression for the EDR query
        filter_expression = [
            {
                "operandLeft": "providerId",
                "operator": "=",
                "operandRight": self.provider_bpn,
            }
        ]
        if asset_id_for_filter:
            filter_expression.append(
                {
                    "operandLeft": "assetId",
                    "operator": "=",
                    "operandRight": asset_id_for_filter,
                }
            )

        payload = {  # QuerySpec payload for EDRs
            "@context": {"@vocab": self.edc_namespace},
            "@type": "QuerySpec",
            "filterExpression": filter_expression,
        }

        start_time = time.time()
        attempt = 0
        try:
            while True:
                attempt += 1
                elapsed_time = time.time() - start_time

                if elapsed_time >= self.edr_polling_timeout_seconds:
                    self.logger.error(
                        f"{operation_name} - Polling timed out after {elapsed_time:.2f}s ({attempt} attempts)."
                    )
                    return None, None

                self.logger.info(
                    f"{operation_name} - Attempt {attempt} ({elapsed_time:.2f}s / {self.edr_polling_timeout_seconds}s)..."
                )

                response_data = self._send_request(
                    "POST",
                    request_url,
                    json_payload=payload,
                    operation_name=f"EDR Polling Attempt {attempt}",
                )

                if isinstance(response_data, dict) and response_data.get("error"):
                    self.logger.warning(
                        f"{operation_name} - Error querying EDRs: {response_data.get('error')}. Retrying..."
                    )
                elif isinstance(
                    response_data, list
                ):  # Successful response is a list of EDR entries
                    self.logger.info(
                        f"{operation_name} - Received {len(response_data)} EDR entries from cache."
                    )
                    for edr_entry in response_data:
                        if isinstance(edr_entry, dict):
                            # If filtering by asset_id, ensure this EDR matches
                            if (
                                asset_id_for_filter
                                and edr_entry.get("assetId") != asset_id_for_filter
                            ):
                                self.logger.debug(
                                    f"  Skipping EDR for asset '{edr_entry.get("assetId")}' (target: '{asset_id_for_filter}')."
                                )
                                continue

                            transfer_process_id = edr_entry.get("transferProcessId")
                            if transfer_process_id:  # Found a finalized EDR
                                success_time = time.time() - start_time
                                self.logger.info(
                                    f"  SUCCESS: Found finalized EDR with transferProcessId: {transfer_process_id} "
                                    f"for asset '{edr_entry.get("assetId", "N/A")}' after {success_time:.2f}s ({attempt} attempts)."
                                )
                                return transfer_process_id, edr_entry
                            else:
                                self.logger.debug(
                                    f"  EDR entry found for asset '{edr_entry.get("assetId", "N/A")}' but no transferProcessId yet."
                                )
                    self.logger.info(
                        f"{operation_name} - No EDR with a transferProcessId found in this batch. Retrying..."
                    )
                else:  # Unexpected response format
                    self.logger.warning(
                        f"{operation_name} - Response was not an error dict or a list (Type: {type(response_data)}). Content (truncated): {str(response_data)[:self.response_print_limit]}. Retrying..."
                    )

                # Re-check timeout before sleeping
                if time.time() - start_time >= self.edr_polling_timeout_seconds:
                    self.logger.error(
                        f"{operation_name} - Polling timed out after {time.time() - start_time:.2f}s ({attempt} attempts) before sleep interval."
                    )
                    return None, None

                self.logger.debug(
                    f"Waiting {self.polling_interval}s before next EDR poll..."
                )
                time.sleep(self.polling_interval)
        finally:
            total_polling_time = time.time() - start_time
            self.logger.info(
                f"{operation_name} - Total EDR polling duration: {total_polling_time:.2f}s over {attempt} attempts."
            )

    def get_data_address(self, edr_id: str) -> dict | None:
        """
        Retrieves the data address for a finalized EDR using its ID from the EDR cache.

        The `edr_id` parameter is the ID of the EDR entry as obtained from the EDR cache
        (e.g., from `get_cached_edrs`, which might be a `transferProcessId` or another unique ID of the cached EDR).

        Args:
            edr_id: The ID of the EDR entry from the cache.

        Returns:
            A dictionary containing the data address if successful, else None.
        """
        operation_name = f"Data Address Retrieval (EDR ID: {edr_id})"
        self.logger.info(operation_name)
        # The edr_id for this GET request is the one obtained from the EDR entry, often transferProcessId
        # or the ID from the initial edrs POST response if that's how the provider maps it.
        request_url = f"{self.base_url.rstrip('/')}/data/v2/edrs/{edr_id}/dataaddress"

        response_data = self._send_request(
            "GET", request_url, operation_name=operation_name
        )

        if response_data and not response_data.get("error"):
            if self.print_response_flag:
                self.logger.info(
                    f"{operation_name} - Data Address Response:\n{self._format_json_for_logging(response_data)}"
                )
            return response_data  # This is the data address object
        else:
            self.logger.error(
                f"{operation_name} - Failed to get data address: {response_data}"
            )
            return None

    def access_data(self, data_address: dict) -> str | None:
        """
        Accesses and downloads data using the provider's endpoint and authorization
        details from the data address.

        The downloaded data is streamed to a file in the configured artifact path.
        The filename is determined from Content-Disposition or a default is used.

        Args:
            data_address: The data address dictionary obtained from `get_data_address`.

        Returns:
            The local file path to the downloaded data if successful, else None.
        """
        operation_name = "Data Access via EDR"
        if self.print_response_flag:
            self.logger.info(
                f"{operation_name} - Using Data Address (auth details might be long):\n{self._format_json_for_logging(data_address)}"
            )

        endpoint = data_address.get("endpoint")

        # Determine the authorization token and its header key.
        # Standard EDRs use "authorization". Some systems might use "authCode".
        auth_token_key = None
        if "authorization" in data_address:  # Standard
            auth_token_key = "authorization"
        elif "authCode" in data_address:  # Fallback for some EDC versions/configs
            auth_token_key = "authCode"

        auth_token_value = data_address.get(auth_token_key) if auth_token_key else None

        if not endpoint or not auth_token_value:
            self.logger.error(
                f"{operation_name} - DataAddress is incomplete. Missing 'endpoint' or token ('authorization'/'authCode'). "
                f"Address Dump:\n{json.dumps(data_address, indent=2)}"
            )
            return None

        headers_for_data_access = {auth_token_key: auth_token_value}
        self.logger.info(
            f"{operation_name} - Accessing data at: {endpoint} using auth header: '{auth_token_key}'."
        )

        # Use _send_request with stream=True and custom headers for data access
        response = self._send_request(
            "GET",
            endpoint,
            headers=headers_for_data_access,  # Use the EDR token, not management API key
            operation_name=f"Data Fetch (Endpoint: {endpoint})",
            stream=True,
        )

        if isinstance(response, requests.Response):  # Successful streaming response
            # Determine filename from Content-Disposition or use a default
            filename = "downloaded_data.dat"  # Default filename
            content_disposition = response.headers.get("Content-Disposition")
            if content_disposition:
                # Basic parsing for filename, e.g., "attachment; filename="actual_filename.txt""
                parts = content_disposition.split("filename=")
                if len(parts) > 1:
                    filename_from_header = (
                        parts[1].strip('"').strip("'")
                    )  # Remove quotes
                    if filename_from_header:
                        filename = filename_from_header

            # Sanitize filename to prevent path traversal or invalid characters
            # Keep only alphanumeric, dot, underscore, hyphen. Replace others with underscore.
            safe_filename = "".join(
                c if c.isalnum() or c in (".", "_", "-") else "_"
                for c in os.path.basename(filename)
            )
            if not safe_filename:  # Ensure there's a filename if all chars were invalid
                safe_filename = f"download_{int(time.time())}.dat"

            file_path = os.path.join(settings.ARTIFACT_DOWNLOAD_PATH, safe_filename)

            self.logger.info(
                f"{operation_name} - Streaming data from {endpoint} to {file_path}"
            )
            try:
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(
                        chunk_size=8192
                    ):  # Process in chunks
                        if chunk:  # filter out keep-alive new chunks
                            f.write(chunk)
                self.logger.info(
                    f"{operation_name} - Data successfully downloaded to: {file_path}"
                )
                return file_path
            except IOError as e:
                self.logger.error(
                    f"{operation_name} - Failed to write downloaded data to {file_path}: {e}"
                )
                return None
            finally:
                response.close()  # Ensure the response is closed
        elif response and response.get(
            "error"
        ):  # Error dictionary returned by _send_request
            self.logger.error(
                f"{operation_name} - Failed to fetch data using EDR: {response.get('error')}"
            )
            return None
        else:  # Unexpected response from _send_request
            self.logger.error(
                f"{operation_name} - Unexpected response type from internal request helper: {type(response)}"
            )
            return None


# Note: Older methods like `execute_full_workflow` or a separate `download_data`
# that might have existed are considered superseded by the more granular methods above,
# orchestrated by the UcController.

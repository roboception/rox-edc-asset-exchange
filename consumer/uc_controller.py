import os
import logging
from .dataspace_client import (
    DataspaceClient,
)  # Removed AssetQuery, EdrRequest, EdrQuery as they are not used
from .config import settings  # Import global settings


class UcController:
    def __init__(self, client: DataspaceClient):
        self.client = client
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(settings.LOG_LEVEL)
        os.makedirs(settings.ARTIFACT_DOWNLOAD_PATH, exist_ok=True)

    def _extract_asset_and_policy_from_dataset(
        self, dataset_data, requested_asset_id=None
    ):
        """
        Extracts asset ID and the first policy object from dataset data.

        Args:
            dataset_data: A single dataset (dict) or a list of datasets.
            requested_asset_id: Optional ID to find a specific asset in a list.

        Returns:
            A tuple (asset_id, full_policy_object) or (None, None) if not found.
        """
        asset_id = None
        full_policy_object = None
        target_dataset = None

        if not dataset_data:
            self.logger.error("Dataset data is empty or None.")
            return None, None

        # If dataset_data is a list, and we have a requested_asset_id, find it.
        # Or, if no requested_asset_id, take the first if it's a list.
        if isinstance(dataset_data, list):
            if not dataset_data:
                self.logger.warning("Received an empty list of datasets.")
                return None, None
            if requested_asset_id:
                found = False
                for item in dataset_data:
                    if isinstance(item, dict) and item.get("@id") == requested_asset_id:
                        target_dataset = item
                        found = True
                        break
                if not found:
                    self.logger.warning(
                        f"Specified asset '{requested_asset_id}' not found in the provided list of datasets."
                    )
                    return None, None
            else:
                target_dataset = dataset_data[
                    0
                ]  # Take the first from the list if no specific ID requested
                self.logger.info(
                    f"No specific asset ID requested from list, using first: {target_dataset.get('@id')}"
                )
        elif isinstance(dataset_data, dict):
            # If it's a single dict, it must be the target dataset.
            # Verify against requested_asset_id if provided.
            if requested_asset_id and dataset_data.get("@id") != requested_asset_id:
                self.logger.warning(
                    f"Provided single dataset '{dataset_data.get('@id')}' does not match requested_asset_id '{requested_asset_id}'."
                    "This might indicate an issue with catalog filtering."
                )
                # Proceeding with the provided dataset, but it might be incorrect if filter failed upstream.
            target_dataset = dataset_data
        else:
            self.logger.error(
                f"Unexpected dataset_data structure: {type(dataset_data)}. Expected dict or list of dicts."
            )
            if self.client.print_response_flag:  # Use the flag from client
                # Attempt to format, but it might not be JSON serializable if it's an unexpected type
                try:
                    formatted_data = self.client._format_json_for_logging(
                        dataset_data
                    )  # Use client's formatter
                    self.logger.error(f"Problematic dataset_data:\n{formatted_data}")
                except Exception as e:
                    self.logger.error(
                        f"Problematic dataset_data (raw, could not format):\n{str(dataset_data)[:settings.RESPONSE_PRINT_LIMIT]}"
                    )
            return None, None

        if target_dataset:
            asset_id = target_dataset.get("@id")
            # EDC policy structure: dataset -> odrl:hasPolicy -> @id (policy_id)
            policies = target_dataset.get("odrl:hasPolicy")
            if policies:
                if isinstance(policies, list) and len(policies) > 0:
                    full_policy_object = policies[
                        0
                    ]  # Take the first full policy object
                    self.logger.info(
                        f"Using first policy object (ID: '{full_policy_object.get('@id')}') from list of {len(policies)} for asset '{asset_id}'."
                    )
                elif isinstance(policies, dict):
                    full_policy_object = policies  # This is the full policy object
                    self.logger.info(
                        f"Using single policy object (ID: '{full_policy_object.get('@id')}') for asset '{asset_id}'."
                    )
                else:
                    self.logger.warning(
                        f"No suitable odrl:hasPolicy found or unexpected format for asset '{asset_id}'. Policies: {policies}"
                    )
            else:
                self.logger.warning(
                    f"Asset '{asset_id}' has no 'odrl:hasPolicy' attribute."
                )
        else:
            self.logger.warning(
                "Could not identify a target dataset from the provided data."
            )

        if not asset_id or not full_policy_object:
            self.logger.error(
                f"Failed to extract valid Asset ID or Full Policy Object. Asset: {asset_id}, Policy Object: {full_policy_object}"
            )
            return None, None

        self.logger.info(
            f"Successfully extracted Asset ID: {asset_id}, Policy Object ID: {full_policy_object.get('@id')}"
        )
        return asset_id, full_policy_object

    def _list_and_select_asset_from_catalog(self, all_datasets):
        """Lists datasets and prompts user for selection."""
        if not all_datasets or not isinstance(all_datasets, list):
            self.logger.error(
                "Cannot list assets: no datasets provided or not in list format."
            )
            return None, None

        self.logger.info("\nAvailable assets:")
        for i, dataset in enumerate(all_datasets):
            self.logger.info(f"  {i+1}. Asset ID: {dataset.get('@id')}")
            # Optionally display more dataset info here

        while True:
            try:
                choice_str = input("Select an asset by number: ")
                choice = int(choice_str) - 1
                if 0 <= choice < len(all_datasets):
                    selected_dataset_item = all_datasets[choice]
                    self.logger.info(
                        f"You selected: {selected_dataset_item.get('@id')}"
                    )
                    # Now extract policy for this selected asset
                    return self._extract_asset_and_policy_from_dataset(
                        selected_dataset_item, selected_dataset_item.get("@id")
                    )
                else:
                    self.logger.error("Invalid selection. Please enter a valid number.")
            except ValueError:
                self.logger.error("Invalid input. Please enter a number.")
            except KeyboardInterrupt:
                self.logger.info("\nSelection cancelled by user.")
                return None, None

    def run_consumer_workflow(self, target_asset_id: str = None):
        """
        Orchestrates the end-to-end consumer workflow for an asset.

        Steps include:
        1. Catalog request (either for a specific asset or listing all).
        2. Contract negotiation initiation (EDR creation).
        3. Polling for finalized EDR in the cache.
        4. Retrieving the data address from the EDR.
        5. Accessing and downloading the data.

        Args:
            target_asset_id: Optional ID of the specific asset to process.
                             If None, lists available assets for user selection.

        Returns:
            The local file path to the downloaded data if successful, else None.
        """
        self.logger.info(
            f"Starting consumer workflow. Target Asset ID: {target_asset_id if target_asset_id else 'ANY (will list)'}"
        )
        retrieved_data_path = None
        asset_id_to_process = None
        policy_object_to_process = None  # Changed from policy_id to full object

        if target_asset_id:
            self.logger.info(
                f"Step 1: Requesting catalog for specific asset: '{target_asset_id}'"
            )
            catalog_data_for_specific_asset = self.client.request_catalog(
                asset_id_filter=target_asset_id
            )
            if catalog_data_for_specific_asset:
                asset_id_to_process, policy_object_to_process = (
                    self._extract_asset_and_policy_from_dataset(
                        catalog_data_for_specific_asset,
                        requested_asset_id=target_asset_id,
                    )
                )
            if not asset_id_to_process or not policy_object_to_process:
                self.logger.warning(
                    f"Failed to find specified asset '{target_asset_id}' or its policy. Offering to list all."
                )
                try:
                    choice = input(
                        "Specified asset not found. List all available assets from the provider? (y/n): "
                    ).lower()
                    if choice != "y":
                        self.logger.info(
                            "User chose not to list assets. Exiting workflow."
                        )
                        return None
                    # Fall through to list all assets if user agrees
                except KeyboardInterrupt:
                    self.logger.info("User cancelled. Exiting workflow.")
                    return None
            else:
                self.logger.info(
                    f"Successfully found and extracted info for target asset: {asset_id_to_process}"
                )

        # If no target_asset_id was specified, or if specified but not found and user agreed to list all
        if not asset_id_to_process or not policy_object_to_process:
            self.logger.info(
                "Step 1: Requesting full catalog to list available assets..."
            )
            all_datasets = self.client.request_catalog()  # No filter, gets all
            if all_datasets:
                asset_id_to_process, policy_object_to_process = (
                    self._list_and_select_asset_from_catalog(all_datasets)
                )
            else:
                self.logger.error("Failed to retrieve any datasets from catalog.")

        if not asset_id_to_process or not policy_object_to_process:
            self.logger.error(
                "No asset and policy object could be determined. Exiting workflow."
            )
            return None

        self.logger.info(
            f"Proceeding with Asset ID: {asset_id_to_process}, Policy Object ID: {policy_object_to_process.get('@id')}"
        )

        # Step 2: Initiate EDR (Contract Request)
        self.logger.info("Step 2: Initiating contract request (EDR)...")
        edr_id, negotiation_details = self.client.initiate_contract(
            asset_id_to_process, policy_object_to_process
        )  # Pass full policy object
        if not edr_id:
            self.logger.error(
                "Failed to initiate EDR (contract negotiation). Exiting workflow."
            )
            return None
        self.logger.info(f"EDR initiated. Negotiation/EDR ID: {edr_id}")
        # negotiation_details might contain contractAgreementId if negotiation is synchronous and fast, or state.
        # The old code implicitly assumed it was more of an EDR ID immediately usable for polling EDR cache.

        # Step 3: Poll for cached EDR to get TransferProcessId
        self.logger.info("Step 3: Polling for cached EDR to find TransferProcessId...")
        transfer_process_id, cached_edr_entry = self.client.get_cached_edrs(
            asset_id_for_filter=asset_id_to_process
        )
        if not transfer_process_id or not cached_edr_entry:
            self.logger.error(
                f"Failed to find a finalized EDR with a TransferProcessId for asset '{asset_id_to_process}'. Exiting workflow."
            )
            return None
        self.logger.info(
            f"Found finalized EDR. TransferProcessId: {transfer_process_id}, EDR Entry ID: {cached_edr_entry.get('@id')}"
        )

        # Step 4: Get Data Address using the EDR ID from the cached EDR entry
        cached_edr_id = cached_edr_entry.get("@id")
        if not cached_edr_id:
            self.logger.error(
                f"Cached EDR entry is missing an '@id'. Cannot get data address. EDR: {cached_edr_entry}"
            )
            return None

        self.logger.info(
            f"Step 4: Retrieving data address using EDR ID: {cached_edr_id}..."
        )
        data_address = self.client.get_data_address(cached_edr_id)
        if not data_address:
            self.logger.error(
                f"Failed to retrieve data address for EDR ID '{cached_edr_id}'. Exiting workflow."
            )
            return None
        # Use client's formatter for consistency if direct printing from settings
        log_data_address = (
            self.client._format_json_for_logging(data_address)
            if settings.PRINT_RESPONSE
            else "(details suppressed)"
        )
        self.logger.info(f"Data address obtained: {log_data_address}")

        # Step 5: Access Data
        self.logger.info("Step 5: Accessing data using the EDR data address...")
        retrieved_data_path = self.client.access_data(data_address)
        if not retrieved_data_path:
            self.logger.error("Failed to access/download data. Exiting workflow.")
            return None

        self.logger.info(
            f"Workflow completed successfully. Data downloaded to: {retrieved_data_path}"
        )
        return retrieved_data_path

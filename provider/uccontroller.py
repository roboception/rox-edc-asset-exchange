import uuid
import os
import logging
from .edcmanager import (
    CreateAccessPolicyDto,
    CreateContractDefinitionDto,
    CreateUsagePolicyDto,
    EdcManager,
    CreateAssetDto,
)
from .objectstoremanager import ObjectStoreManager
from .config import settings


class UcController:
    """Orchestrates provider-side use cases, including EDC asset lifecycle and S3 uploads."""

    edcManager: EdcManager
    objectStoreManager: ObjectStoreManager

    def __init__(
        self,
        edcManager: EdcManager,
        objectStoreManager: ObjectStoreManager,
    ):
        """Initializes UcController with EDC, ObjectStore, and Roboception managers."""
        self.edcManager = edcManager
        self.objectStoreManager = objectStoreManager
        self.temp_dir = "/tmp/provider_temp"
        os.makedirs(self.temp_dir, exist_ok=True)
        self.logger = logging.getLogger(__name__)
        # Main.py or provider_app.py should configure logging level based on settings

    def _determine_bpn_for_policy(self) -> str | None:
        """Determines the Consumer BPN for policy creation, primarily from settings.CONSUMER_BPN."""
        if settings.CONSUMER_BPN:
            self.logger.info(
                f"Using CONSUMER_BPN from settings for policy: {settings.CONSUMER_BPN}"
            )
            return settings.CONSUMER_BPN

        self.logger.warning(
            f"CONSUMER_BPN not set in settings. Cannot create policies targeted to a specific consumer."
        )
        return None

    def _create_dataspace_entries(self, asset_id: str, s3_filename: str):
        """Creates all necessary EDC entities (Asset, Policies, Contract Definition) for a given S3 object."""
        res = {"assetId": asset_id}
        success = True
        bucket_name = settings.DEFAULT_BUCKET_NAME
        if not bucket_name:
            self.logger.error(
                "settings.DEFAULT_BUCKET_NAME is not set. Cannot create S3-backed asset."
            )
            return None

        bpn_for_policy = self._determine_bpn_for_policy()
        if not bpn_for_policy:
            self.logger.error(
                "Consumer BPN for policy creation not determined. Cannot create policies or contract definition."
            )
            return {"assetId": asset_id, "error": "CONSUMER_BPN_NOT_CONFIGURED"}

        self.logger.info(
            f"Using BPN: {bpn_for_policy} for policies for asset '{asset_id}'."
        )

        createAssetDto = CreateAssetDto(
            assetId=asset_id, bucketName=bucket_name, fileName=s3_filename
        )
        self.logger.info(
            f"Creating/verifying asset '{asset_id}' in bucket '{bucket_name}'."
        )
        asset_response = self.edcManager.createAsset(createAssetDto)

        if not (
            asset_response
            and (
                asset_response.get("@id") or asset_response.get("status") == "conflict"
            )
        ):
            self.logger.error(
                f"Asset creation/verification failed for '{asset_id}'. Response: {asset_response}"
            )
            return None
        self.logger.info(f"Asset '{asset_id}' processed successfully.")

        asset_id_prefix = str(asset_id)[:18] if asset_id else "asset"
        access_policy_id = f"ap-{asset_id_prefix}-{str(uuid.uuid4())[:8]}"
        usage_policy_id = f"up-{asset_id_prefix}-{str(uuid.uuid4())[:8]}"
        contract_definition_id = f"cd-{asset_id_prefix}-{str(uuid.uuid4())[:8]}"

        createAccessPolicyDto = CreateAccessPolicyDto(
            accessPolicyId=access_policy_id, bpn=bpn_for_policy
        )
        self.logger.info(f"Creating Access Policy '{access_policy_id}'.")
        policy_response = self.edcManager.createAccessPolicy(createAccessPolicyDto)
        if policy_response and (
            policy_response.get("@id") or policy_response.get("status") == "conflict"
        ):
            res["accessPolicyId"] = access_policy_id
        else:
            self.logger.error(
                f"Failed to create/verify Access Policy '{access_policy_id}'. Resp: {policy_response}"
            )
            success = False

        createUsagePolicyDto = CreateUsagePolicyDto(
            usagePolicyId=usage_policy_id, bpn=bpn_for_policy
        )
        self.logger.info(f"Creating Usage Policy '{usage_policy_id}'.")
        policy_response = self.edcManager.createUsagePolicy(createUsagePolicyDto)
        if policy_response and (
            policy_response.get("@id") or policy_response.get("status") == "conflict"
        ):
            res["usagePolicyId"] = usage_policy_id
        else:
            self.logger.error(
                f"Failed to create/verify Usage Policy '{usage_policy_id}'. Resp: {policy_response}"
            )
            success = False

        if "accessPolicyId" in res and "usagePolicyId" in res:
            createCDDto = CreateContractDefinitionDto(
                contractDefinitionId=contract_definition_id,
                accessPolicyId=res["accessPolicyId"],
                usagePolicyId=res["usagePolicyId"],
                assetId=asset_id,
            )
            self.logger.info(
                f"Creating Contract Definition '{contract_definition_id}'."
            )
            cd_response = self.edcManager.createContractDefinition(createCDDto)
            if cd_response and (
                cd_response.get("@id") or cd_response.get("status") == "conflict"
            ):
                res["contractDefinitionId"] = contract_definition_id
            else:
                self.logger.error(
                    f"Failed to create/verify Contract Definition '{contract_definition_id}'. Resp: {cd_response}"
                )
                success = False
        else:
            self.logger.warning(
                f"Skipping Contract Definition for asset '{asset_id}' due to policy creation issues."
            )
            success = False

        return res if success else {**res, "error": "POLICY_OR_CD_CREATION_FAILED"}

    def process_snapshot_and_create_asset(
        self, downloaded_tarball_path: str, original_tarball_type: str
    ):
        """Processes a downloaded snapshot tarball, uploads to S3, and creates EDC entries."""
        self.logger.info(
            f"Processing snapshot: {downloaded_tarball_path} of type {original_tarball_type}"
        )
        if not (downloaded_tarball_path and os.path.isfile(downloaded_tarball_path)):
            self.logger.error(
                f"Invalid snapshot tarball path: {downloaded_tarball_path}"
            )
            return None

        s3_object_name = f"{original_tarball_type}_{str(uuid.uuid4())[:12]}.tar.gz"
        bucket_name = settings.DEFAULT_BUCKET_NAME
        if not bucket_name:
            self.logger.error(
                "settings.DEFAULT_BUCKET_NAME not set. Cannot upload to S3."
            )
            return {"error": "S3_BUCKET_NOT_CONFIGURED"}

        self.logger.info(f"Uploading {s3_object_name} to S3 bucket {bucket_name}...")
        try:
            self.objectStoreManager.assertBucket(bucket_name)
            self.objectStoreManager.uploadFile(
                bucket_name, s3_object_name, downloaded_tarball_path
            )
            self.logger.info(f"Successfully uploaded {s3_object_name} to S3.")
        except Exception as e:
            self.logger.exception(
                f"Error uploading {s3_object_name} to S3."
            )  # Use .exception for stack trace
            return {"s3_object_name": s3_object_name, "error": f"S3_UPLOAD_FAILED: {e}"}

        asset_id = s3_object_name  # Use the S3 object name as the EDC asset ID
        edc_entities = self._create_dataspace_entries(asset_id, s3_object_name)

        if edc_entities and not edc_entities.get("error"):
            self.logger.info(
                f"Successfully created EDC entries for snapshot asset {asset_id}"
            )
            return edc_entities
        else:
            self.logger.error(
                f"Failed EDC registration for {asset_id}. S3 object: {s3_object_name}. Details: {edc_entities}"
            )
            return {
                **edc_entities,
                "s3_object_name": s3_object_name,
                "final_status": "EDC_REGISTRATION_INCOMPLETE",
            }

    def executeUc3(self, asset_id_param: str = None):
        """Executes a default use case: creates a dummy file, uploads to S3, and registers in EDC."""
        self.logger.info(
            f"Executing default asset creation (UC3) with asset_id_param: {asset_id_param}"
        )
        bucket_name = settings.DEFAULT_BUCKET_NAME
        if not bucket_name:
            self.logger.error(
                "settings.DEFAULT_BUCKET_NAME not set for UC3. Cannot proceed."
            )
            return None

        assetIdToRegister = (
            asset_id_param if asset_id_param else settings.DEFAULT_ASSET_NAME
        )
        if not assetIdToRegister:
            assetIdToRegister = f"sample-asset-{str(uuid.uuid4())[:8]}"
            self.logger.info(
                f"No asset_id specified, generated new: {assetIdToRegister}"
            )
        else:
            self.logger.info(f"Using asset_id: {assetIdToRegister}")

        unique_temp_id = str(uuid.uuid4())[:8]
        sourceFileNameOnDisk = os.path.join(
            self.temp_dir, f"dummy_content_{unique_temp_id}.json"
        )
        s3_destinationFileName = f"sample_content_{unique_temp_id}.json"

        try:
            with open(sourceFileNameOnDisk, "w") as f:
                f.write(
                    '{"message": "Hello from default asset via UC3", "id": "'
                    + assetIdToRegister
                    + '"}'
                )

            self.objectStoreManager.assertBucket(bucket_name)
            self.logger.info(
                f"Uploading '{sourceFileNameOnDisk}' as '{s3_destinationFileName}' to '{bucket_name}'."
            )
            self.objectStoreManager.uploadFile(
                bucket_name, s3_destinationFileName, sourceFileNameOnDisk
            )
        except Exception as e:
            self.logger.exception(
                "Error during dummy file creation or S3 upload in UC3."
            )  # Use .exception
            return None
        finally:
            if os.path.exists(sourceFileNameOnDisk):
                try:
                    os.remove(sourceFileNameOnDisk)
                except OSError as e:
                    self.logger.warning(
                        f"Could not remove temp file {sourceFileNameOnDisk}: {e}"
                    )  # Log warning

        edc_entities = self._create_dataspace_entries(
            assetIdToRegister, s3_destinationFileName
        )

        if edc_entities and not edc_entities.get("error"):
            self.logger.info(
                f"UC3 completed successfully for asset {assetIdToRegister}"
            )
        else:
            self.logger.error(
                f"UC3 failed or had issues creating EDC entities for asset {assetIdToRegister}. Details: {edc_entities}"
            )
        return edc_entities

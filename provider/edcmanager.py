from pydantic import BaseModel
import requests
import logging
from .config import settings  # Import global settings

# Environment loading is now done in main.py


class CreateAssetDto(BaseModel):
    """Data Transfer Object for creating an asset."""

    assetId: str
    bucketName: str
    fileName: str


class GetAssetDto(BaseModel):
    """Data Transfer Object for retrieving an asset."""

    assetId: str


class CreateAccessPolicyDto(BaseModel):
    """Data Transfer Object for creating an access policy."""

    accessPolicyId: str
    bpn: str


class GetAccessPolicyDto(BaseModel):
    """Data Transfer Object for retrieving an access policy."""

    accessPolicyId: str


class CreateUsagePolicyDto(BaseModel):
    """Data Transfer Object for creating a usage policy."""

    usagePolicyId: str
    bpn: str


class GetUsagePolicyDto(BaseModel):
    """Data Transfer Object for retrieving a usage policy."""

    usagePolicyId: str


class CreateContractDefinitionDto(BaseModel):
    """Data Transfer Object for creating a contract definition."""

    contractDefinitionId: str
    accessPolicyId: str
    usagePolicyId: str
    assetId: str


class GetContractDefinitionDto(BaseModel):
    """Data Transfer Object for retrieving a contract definition."""

    contractDefinitionId: str


class EdcManager:
    """Manages interactions with the EDC Control Plane for assets, policies, and contract definitions."""

    def __init__(self):
        """Initializes EdcManager with base URL and API key from settings."""
        if not settings.BASE_URL or not settings.API_KEY:
            raise ValueError(
                "EdcManager: BASE_URL or API_KEY not configured in settings."
            )

        self.EdcConnectorUrl = settings.BASE_URL
        self.DataManagementApiEndpoint = self.EdcConnectorUrl + "/data"
        self.EdcApiKey = settings.API_KEY
        self.last_response_status_code = None
        self.logger = logging.getLogger(__name__)

    def _send_request(
        self,
        method: str,
        url: str,
        payload: dict = None,
        success_status_codes: list = None,
        operation_name: str = "Operation",
    ):
        if success_status_codes is None:
            success_status_codes = [200]

        headers = {"X-API-Key": self.EdcApiKey}
        if method.upper() == "POST" and payload is not None:
            headers["Content-Type"] = "application/json"

        self.logger.debug(
            f"{operation_name} - Method: {method}, URL: {url}, Payload: {payload if payload else 'N/A'}"
        )

        try:
            req = requests.request(
                method.upper(),
                url,
                json=payload if method.upper() == "POST" else None,
                headers=headers,
            )
            self.last_response_status_code = req.status_code
            self.logger.info(f"{operation_name} - Status Code: {req.status_code}")

            if req.status_code in success_status_codes:
                if req.status_code == 409:
                    self.logger.warning(
                        f"{operation_name} - Resource already exists (Status 409). ID: {payload.get('@id') if payload else 'N/A'}"
                    )
                    return {
                        "status": "conflict",
                        "id": payload.get("@id") if payload else None,
                    }
                if not req.content:
                    return {
                        "status": "success_no_content",
                        "status_code": req.status_code,
                    }
                return req.json()
            else:
                self.logger.error(
                    f"{operation_name} - Failed with status {req.status_code}. Response: {req.text[:500]}"
                )
                return None
        except requests.exceptions.RequestException as ex:
            self.logger.error(f"{operation_name} - Request error occurred: {ex}")
            self.last_response_status_code = None
            return None

    def createAsset(self, createAssetDto: CreateAssetDto):
        """Creates a new asset definition in the EDC, pointing to an S3 data source."""
        url = self.DataManagementApiEndpoint + "/v3/assets"

        self.logger.info(
            f"Registering asset with S3 configuration: Endpoint: {settings.S3_ENDPOINT}, Bucket: {createAssetDto.bucketName}"
        )

        if not all(
            [settings.S3_ENDPOINT, settings.S3_ACCESS_KEY, settings.S3_SECRET_KEY]
        ):
            self.logger.error(
                "S3 configuration (ENDPOINT, ACCESS_KEY, SECRET_KEY) missing in settings."
            )
            return None

        payload = {
            "@context": {"edc": "https://w3id.org/edc/v0.0.1/ns/"},
            "@id": createAssetDto.assetId,
            "properties": {
                "description": "Generic Test Asset",
                "edc:originator": settings.PROVIDER_BPN,
                "metadata.volume": "1GB",
                "contenttype": "application/json",
            },
            "privateProperties": {"assetOwner": "Provider Organization"},
            "dataAddress": {
                "@type": "DataAddress",
                "type": "AmazonS3",
                "region": settings.S3_REGION,
                "endpointOverride": f"https://{settings.S3_ENDPOINT}/",
                "bucketName": createAssetDto.bucketName,
                "keyName": createAssetDto.fileName,
                "accessKeyId": settings.S3_ACCESS_KEY,
                "secretAccessKey": settings.S3_SECRET_KEY,
            },
        }
        return self._send_request(
            "POST",
            url,
            payload,
            success_status_codes=[200, 409],
            operation_name=f"Create Asset {createAssetDto.assetId}",
        )

    def getAsset(self, getAssetDto: GetAssetDto):
        """Retrieves an asset definition by its ID."""
        url = f"{self.DataManagementApiEndpoint}/v3/assets/{getAssetDto.assetId}"
        return self._send_request(
            "GET", url, operation_name=f"Get Asset {getAssetDto.assetId}"
        )

    def _create_policy_payload(self, policy_id: str, bpn: str):
        """Helper method to construct the JSON payload for a policy definition."""
        return {
            "@id": policy_id,
            "@type": "edc:PolicyDefinition",
            "policy": {
                "@id": policy_id,
                "@type": "odrl:Set",
                "odrl:permission": {
                    "odrl:action": {"@id": "odrl:use"},
                    "odrl:constraint": {
                        "odrl:or": {
                            "odrl:leftOperand": {"@id": "BusinessPartnerNumber"},
                            "odrl:operator": {"@id": "odrl:eq"},
                            "odrl:rightOperand": bpn,
                        }
                    },
                },
                "odrl:prohibition": [],
                "odrl:obligation": [],
            },
            "@context": {
                "@vocab": "https://w3id.org/edc/v0.0.1/ns/",
                "edc": "https://w3id.org/edc/v0.0.1/ns/",
                "tx": "https://w3id.org/tractusx/v0.0.1/ns/",
                "tx-auth": "https://w3id.org/tractusx/auth/",
                "cx-policy": "https://w3id.org/catenax/policy/",
                "odrl": "http://www.w3.org/ns/odrl/2/",
            },
        }

    def createAccessPolicy(self, createAccessPolicyDto: CreateAccessPolicyDto):
        """Creates an access policy definition in the EDC."""
        url = self.DataManagementApiEndpoint + "/v2/policydefinitions"
        payload = self._create_policy_payload(
            createAccessPolicyDto.accessPolicyId, createAccessPolicyDto.bpn
        )
        return self._send_request(
            "POST",
            url,
            payload,
            success_status_codes=[200, 409],
            operation_name=f"Create Access Policy {createAccessPolicyDto.accessPolicyId}",
        )

    def getAccessPolicy(self, getAccessPolicyDto: GetAccessPolicyDto):
        """Retrieves an access policy definition by its ID."""
        url = f"{self.DataManagementApiEndpoint}/v2/policydefinitions/{getAccessPolicyDto.accessPolicyId}"
        return self._send_request(
            "GET",
            url,
            operation_name=f"Get Access Policy {getAccessPolicyDto.accessPolicyId}",
        )

    def createUsagePolicy(self, createUsagePolicyDto: CreateUsagePolicyDto):
        """Creates a usage policy definition in the EDC."""
        url = self.DataManagementApiEndpoint + "/v2/policydefinitions"
        payload = self._create_policy_payload(
            createUsagePolicyDto.usagePolicyId, createUsagePolicyDto.bpn
        )
        return self._send_request(
            "POST",
            url,
            payload,
            success_status_codes=[200, 409],
            operation_name=f"Create Usage Policy {createUsagePolicyDto.usagePolicyId}",
        )

    def getUsagePolicy(self, getUsagePolicyDto: GetUsagePolicyDto):
        """Retrieves a usage policy definition by its ID."""
        url = f"{self.DataManagementApiEndpoint}/v2/policydefinitions/{getUsagePolicyDto.usagePolicyId}"
        return self._send_request(
            "GET",
            url,
            operation_name=f"Get Usage Policy {getUsagePolicyDto.usagePolicyId}",
        )

    def createContractDefinition(
        self, createContractDefinitionDto: CreateContractDefinitionDto
    ):
        """Creates a contract definition in the EDC, linking asset(s) to policies."""
        url = self.DataManagementApiEndpoint + "/v2/contractdefinitions"
        payload = {
            "@context": {},
            "@id": createContractDefinitionDto.contractDefinitionId,
            "@type": "ContractDefinition",
            "accessPolicyId": createContractDefinitionDto.accessPolicyId,
            "contractPolicyId": createContractDefinitionDto.usagePolicyId,
            "assetsSelector": [
                {
                    "@type": "CriterionDto",
                    "operandLeft": "https://w3id.org/edc/v0.0.1/ns/id",
                    "operator": "=",
                    "operandRight": createContractDefinitionDto.assetId,
                }
            ],
        }
        return self._send_request(
            "POST",
            url,
            payload,
            success_status_codes=[200, 409],
            operation_name=f"Create Contract Definition {createContractDefinitionDto.contractDefinitionId}",
        )

    def getContractDefinition(self, getContractDefinitionDto: GetContractDefinitionDto):
        """Retrieves a contract definition by its ID."""
        url = f"{self.DataManagementApiEndpoint}/v2/contractdefinitions/{getContractDefinitionDto.contractDefinitionId}"
        return self._send_request(
            "GET",
            url,
            operation_name=f"Get Contract Definition {getContractDefinitionDto.contractDefinitionId}",
        )

import os


class Settings:
    BASE_URL: str = None  # Provider's EDC Management API base URL
    API_KEY: str = None  # Provider's EDC Management API key
    EDC_NAMESPACE: str = None
    DEFAULT_ASSET_NAME: str = None
    PRINT_RESPONSE: bool = False
    EDR_POLLING_TIMEOUT_SECONDS: int = 30
    LOG_LEVEL: str = "INFO"
    ARTIFACT_DOWNLOAD_PATH: str = "/tmp/consumer_artifacts"
    RESPONSE_PRINT_LIMIT: int = 3000  # Max characters to print for response text
    PRINT_FIRST_JSON_ELEMENT_ONLY: bool = True  # New setting
    CATALOG_REQUEST_LIMIT: int = (
        500  # Max number of assets to request in a catalog call
    )

    # BPN of the target provider
    PROVIDER_BPN: str = None

    def load_from_env(self):
        """Populates settings from OS environment variables."""
        self.BASE_URL = os.getenv("BASE_URL")
        self.API_KEY = os.getenv("API_KEY")
        self.EDC_NAMESPACE = os.getenv(
            "EDC_NAMESPACE", "https://w3id.org/edc/v0.0.1/ns/"
        )
        self.DEFAULT_ASSET_NAME = os.getenv("DEFAULT_ASSET_NAME")
        self.PRINT_RESPONSE = os.getenv("PRINT_RESPONSE", "false").lower() == "true"
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
        self.ARTIFACT_DOWNLOAD_PATH = os.getenv(
            "ARTIFACT_DOWNLOAD_PATH", "/tmp/consumer_artifacts"
        )
        try:
            self.EDR_POLLING_TIMEOUT_SECONDS = int(
                os.getenv("EDR_POLLING_TIMEOUT_SECONDS", "30")
            )
        except ValueError:
            print(
                f"Warning: Invalid EDR_POLLING_TIMEOUT_SECONDS value. Defaulting to 30."
            )
            self.EDR_POLLING_TIMEOUT_SECONDS = 30
        try:
            self.RESPONSE_PRINT_LIMIT = int(os.getenv("RESPONSE_PRINT_LIMIT", "3000"))
        except ValueError:
            print(f"Warning: Invalid RESPONSE_PRINT_LIMIT value. Defaulting to 3000.")
            self.RESPONSE_PRINT_LIMIT = 3000
        try:
            self.CATALOG_REQUEST_LIMIT = int(os.getenv("CATALOG_REQUEST_LIMIT", "500"))
        except ValueError:
            print(f"Warning: Invalid CATALOG_REQUEST_LIMIT value. Defaulting to 500.")
            self.CATALOG_REQUEST_LIMIT = 500
        self.PRINT_FIRST_JSON_ELEMENT_ONLY = (
            os.getenv("PRINT_FIRST_JSON_ELEMENT_ONLY", "true").lower() == "true"
        )

        self.PROVIDER_BPN = os.getenv("PROVIDER_BPN")  # Load generic PROVIDER_BPN

        # Critical environment variables check
        if not self.BASE_URL:
            raise ValueError(
                "CRITICAL: BASE_URL (Provider's EDC Management API) environment variable not set."
            )
        if not self.API_KEY:
            raise ValueError(
                "CRITICAL: API_KEY (Provider's EDC Management API) environment variable not set."
            )
        if not self.PROVIDER_BPN:  # Check the generic PROVIDER_BPN
            raise ValueError("CRITICAL: PROVIDER_BPN (Target Provider BPN) not set.")


settings = Settings()

# Example of how to update logging based on these settings
# This would typically be done in main.py after loading .env and then settings.load_from_env()
# import logging
# logging.basicConfig(level=settings.LOG_LEVEL)

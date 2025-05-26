import os


class Settings:
    # EDC Connector Settings
    BASE_URL: str = None
    API_KEY: str = None

    # BPN Information
    PROVIDER_BPN: str = None  # BPN of this provider
    CONSUMER_BPN: str = None  # BPN of the consumer for policy creation

    # S3 Storage Settings
    S3_ENDPOINT: str = None
    S3_ACCESS_KEY: str = None
    S3_SECRET_KEY: str = None
    S3_REGION: str = "eu-central-1"  # Default S3 region, can be overridden by env
    DEFAULT_BUCKET_NAME: str = None
    S3_SECURE: bool = True  # For Minio client, True for HTTPS, False for HTTP

    # Application Behavior
    LOG_LEVEL: str = "INFO"
    DEFAULT_ASSET_NAME: str = None  # Default asset ID if not provided by caller
    PRINT_RESPONSE: bool = False
    RESPONSE_PRINT_LIMIT: int = 3000
    PRINT_FIRST_JSON_ELEMENT_ONLY: bool = True

    # Settings for specific device/snapshot interactions (e.g., Roboception)
    RC_HOST: str = None
    RC_PIPELINE: int = 0
    # SNAPSHOT_TYPE is loaded by main.py if/when calling snapshot functionality directly

    def load_from_env(self):
        """Populates settings from OS environment variables."""
        self.BASE_URL = os.getenv("BASE_URL")
        self.API_KEY = os.getenv("API_KEY")

        self.PROVIDER_BPN = os.getenv("PROVIDER_BPN")
        self.CONSUMER_BPN = os.getenv("CONSUMER_BPN")

        self.S3_ENDPOINT = os.getenv("S3_ENDPOINT")
        self.S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY")
        self.S3_SECRET_KEY = os.getenv("S3_SECRET_KEY")
        self.S3_REGION = os.getenv("S3_REGION", "ap-northeast-1")
        self.DEFAULT_BUCKET_NAME = os.getenv("DEFAULT_BUCKET_NAME")
        s3_secure_str = os.getenv("S3_SECURE", "true").lower()
        self.S3_SECURE = s3_secure_str == "true"

        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
        self.DEFAULT_ASSET_NAME = os.getenv(
            "DEFAULT_ASSET_NAME", f"default-asset-from-config"
        )
        self.PRINT_RESPONSE = os.getenv("PRINT_RESPONSE", "false").lower() == "true"
        try:
            self.RESPONSE_PRINT_LIMIT = int(os.getenv("RESPONSE_PRINT_LIMIT", "3000"))
        except ValueError:
            print(
                f"Warning: Invalid RESPONSE_PRINT_LIMIT value for provider. Defaulting to 3000."
            )
            self.RESPONSE_PRINT_LIMIT = 3000
        self.PRINT_FIRST_JSON_ELEMENT_ONLY = (
            os.getenv("PRINT_FIRST_JSON_ELEMENT_ONLY", "true").lower() == "true"
        )

        # Load device/snapshot specific settings
        self.RC_HOST = os.getenv("RC_HOST")
        try:
            self.RC_PIPELINE = int(os.getenv("RC_PIPELINE", "0"))
        except ValueError:
            print(
                f"Warning: Invalid RC_PIPELINE value '{os.getenv("RC_PIPELINE")}'. Defaulting to 0."
            )
            self.RC_PIPELINE = 0

        # Critical environment variables check
        if not self.BASE_URL:
            raise ValueError("CRITICAL: BASE_URL environment variable not set.")
        if not self.API_KEY:
            raise ValueError("CRITICAL: API_KEY environment variable not set.")
        if not self.PROVIDER_BPN:
            raise ValueError("CRITICAL: PROVIDER_BPN environment variable not set.")
        # RC_HOST is not critical for all operations, RoboceptionManager checks for it.


# Global settings instance
settings = Settings()

# Example of how to update logging based on these settings
# This would typically be done in main.py after loading .env and then settings.load_from_env()
# import logging
# logging.basicConfig(level=settings.LOG_LEVEL)

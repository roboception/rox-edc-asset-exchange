from minio import Minio
from minio.error import S3Error
import logging
from .config import settings


class ObjectStoreManager:
    """Manages interactions with an S3-compatible object store (e.g., Minio).

    Handles client initialization, bucket creation/checking, and file uploads/downloads.
    Configuration is sourced from the global `settings` object.
    """

    def __init__(self):
        """Initializes the ObjectStoreManager.

        Sets up the Minio S3 client based on environment variables loaded into `settings`.
        If essential S3 configuration is missing, logs a warning and the client remains uninitialized,
        causing subsequent operations to fail.
        """
        self.logger = logging.getLogger(__name__)
        self.s3client: Minio | None = None  # Initialize to None with type hint

        if (
            not settings.S3_ENDPOINT
            or not settings.S3_ACCESS_KEY
            or not settings.S3_SECRET_KEY
        ):
            self.logger.warning(
                "Minio S3 client not configured (S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY missing). "
                "Operations requiring S3 will fail."
            )
            return

        try:
            self.logger.info(
                f"Initializing Minio client for endpoint: {settings.S3_ENDPOINT}, secure: {settings.S3_SECURE}"
            )
            self.s3client = Minio(
                settings.S3_ENDPOINT,
                access_key=settings.S3_ACCESS_KEY,
                secret_key=settings.S3_SECRET_KEY,
                secure=settings.S3_SECURE,
            )
            # Optional: A quick check like list_buckets can verify connectivity if needed.
            # self.s3client.list_buckets()
            self.logger.info("Minio S3 client initialized successfully.")
        except S3Error as err:
            self.logger.error(f"S3Error during Minio S3 client initialization: {err}")
            self.s3client = None  # Ensure client is None if initialization fails
        except (
            Exception
        ) as e:  # Catch other potential errors (e.g., invalid endpoint format)
            self.logger.error(
                f"A non-S3 error occurred during Minio client initialization: {e}"
            )
            self.s3client = None

    def _client_ready(self) -> bool:
        """Checks if the Minio S3 client is initialized and ready for operations."""
        if not self.s3client:
            self.logger.error(
                "Minio S3 client is not initialized. Check S3 configuration and startup logs."
            )
            return False
        return True

    def assertBucket(self, bucket_name: str):
        """Ensures a bucket exists in the S3 store. If not, it attempts to create it.

        Args:
            bucket_name: The name of the bucket to check or create.

        Raises:
            ConnectionError: If the S3 client is not initialized.
            S3Error: If an error occurs during S3 operations.
        """
        if not self._client_ready():
            # Logged in _client_ready, raising to signal failure is sufficient here.
            raise ConnectionError("Minio S3 client not ready. Cannot assert bucket.")
        try:
            found = self.s3client.bucket_exists(bucket_name)
            if not found:
                self.s3client.make_bucket(bucket_name)
                self.logger.info(f"Bucket '{bucket_name}' created successfully.")
            else:
                self.logger.debug(
                    f"Bucket '{bucket_name}' already exists."
                )  # Changed to debug for less noise
        except S3Error as err:
            self.logger.error(f"S3 error while asserting bucket '{bucket_name}': {err}")
            raise

    def uploadFile(self, bucket_name: str, object_name: str, file_path: str):
        """Uploads a local file to the specified S3 bucket.

        Args:
            bucket_name: The name of the target S3 bucket.
            object_name: The desired name for the object in S3.
            file_path: The local path to the file to be uploaded.

        Raises:
            ConnectionError: If the S3 client is not initialized.
            FileNotFoundError: If the `file_path` does not exist (raised by Minio client).
            S3Error: If an error occurs during S3 upload.
        """
        if not self._client_ready():
            raise ConnectionError("Minio S3 client not ready. Cannot upload file.")

        # The os.path.exists check is removed; Minio's fput_object handles FileNotFoundError.

        try:
            self.logger.info(
                f"Uploading '{file_path}' to S3 destination: '{bucket_name}/{object_name}'."
            )
            self.s3client.fput_object(bucket_name, object_name, file_path)
            self.logger.info(
                f"Successfully uploaded '{file_path}' to '{bucket_name}/{object_name}'."
            )
        except (
            FileNotFoundError
        ):  # Specific catch for clarity, though S3Error might also cover some cases
            self.logger.error(f"Source file for S3 upload not found: {file_path}")
            raise
        except S3Error as err:
            self.logger.error(f"S3 error during upload of file '{file_path}': {err}")
            raise

    def downloadFile(self, bucket_name: str, object_name: str, file_path: str):
        """Downloads an object from S3 to a local file.

        Args:
            bucket_name: The name of the S3 bucket.
            object_name: The name of the object in S3 to download.
            file_path: The local path where the downloaded file should be saved.

        Raises:
            ConnectionError: If the S3 client is not initialized.
            S3Error: If an error occurs during S3 download (e.g., object not found).
        """
        if not self._client_ready():
            raise ConnectionError("Minio S3 client not ready. Cannot download file.")
        try:
            self.logger.info(
                f"Downloading S3 object '{bucket_name}/{object_name}' to local path '{file_path}'."
            )
            self.s3client.fget_object(bucket_name, object_name, file_path)
            self.logger.info(
                f"Successfully downloaded '{object_name}' to '{file_path}'."
            )
        except S3Error as err:
            self.logger.error(
                f"S3 error downloading object '{object_name}' from bucket '{bucket_name}': {err}"
            )
            raise

from .edcmanager import EdcManager
from .objectstoremanager import ObjectStoreManager
from .uccontroller import UcController
from .config import settings
import argparse
import os
from dotenv import load_dotenv
import logging
import uuid

logger = logging.getLogger(__name__)


def setup_logging():
    """Configures basic logging using LOG_LEVEL from settings."""
    log_level_to_use = settings.LOG_LEVEL  # Assumes settings are loaded

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=log_level_to_use,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    else:
        logging.getLogger().setLevel(log_level_to_use)

    logger.info(f"Logging configured to level: {log_level_to_use}")


def main(asset_id: str = None, env_file: str = None):
    """Main entry point for the provider application.

    Handles argument parsing, environment loading, settings initialization,
    logging setup, and use case execution.
    Accepts asset_id and env_file programmatically for testing/integration.
    """

    # Determine effective asset_id and env_file based on params or CLI args
    effective_asset_id = asset_id
    effective_env_file = env_file

    # If not called with parameters (e.g., run as script), use argparse
    # This condition means it's likely invoked from command line directly
    if asset_id is None and env_file is None:
        parser = argparse.ArgumentParser(description="Dataspace Provider Application")
        parser.add_argument(
            "--env-file",
            dest="cli_env_file",
            type=str,
            default=os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "provider.env"
            ),
            help="Path to the .env file to load. Defaults to 'provider.env' in the script directory.",
        )
        parser.add_argument(
            "asset_id_cli",
            nargs="?",
            default=None,
            help="Optional asset ID to use for the operation. Overrides settings.DEFAULT_ASSET_NAME.",
        )
        args = parser.parse_args()
        effective_asset_id = args.asset_id_cli
        effective_env_file = args.cli_env_file
    elif (
        effective_env_file is None
    ):  # Programmatic call, but env_file was not specified
        # Default to 'provider.env' if only asset_id is given programmatically
        effective_env_file = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "provider.env"
        )

    # At this point, effective_env_file should be set either by param, CLI, or default for programmatic call.
    # effective_asset_id can still be None if not provided by param or CLI.

    env_file_to_load = os.path.abspath(effective_env_file)

    # 1. Load .env file
    if os.path.exists(env_file_to_load):
        print(
            f"INFO: Loading environment from: {env_file_to_load}"
        )  # Print as logger not yet configured
        load_dotenv(env_file_to_load, override=True)
    else:
        print(f"CRITICAL: Environment file not found at {env_file_to_load}. Exiting.")
        return  # Or raise error if called programmatically

    # 2. Populate global settings object and Setup Logging
    try:
        settings.load_from_env()
    except ValueError as e:
        print(
            f"CRITICAL: Configuration error: {e}. Check .env file and settings.py. Exiting."
        )
        return

    setup_logging()
    logger.info(f"Successfully loaded environment from: {env_file_to_load}")

    # 3. Determine Asset ID to use (CLI/param > settings.DEFAULT_ASSET_NAME > generated)
    asset_id_to_use = effective_asset_id
    if not asset_id_to_use:
        asset_id_to_use = settings.DEFAULT_ASSET_NAME
        if not asset_id_to_use:
            asset_id_to_use = f"generated-asset-{str(uuid.uuid4())[:8]}"
            logger.info(
                f"No asset_id provided via CLI/param or settings; generated: {asset_id_to_use}"
            )
        else:
            logger.info(
                f"No asset_id provided via CLI/param; using from settings.DEFAULT_ASSET_NAME: {asset_id_to_use}"
            )
    else:
        logger.info(
            f"Using asset_id from CLI argument or function parameter: {asset_id_to_use}"
        )

    logger.info("Initializing application components...")
    try:
        edc_manager = EdcManager()
        object_store_manager = ObjectStoreManager()
        if not object_store_manager.s3client:
            logger.critical(
                "S3 ObjectStoreManager failed to initialize its client. UC3 requires S3. Exiting."
            )
            return

        uc_controller = UcController(edc_manager, object_store_manager)

    except Exception as e:
        logger.exception("Fatal error during component initialization. Exiting.")
        return

    logger.info(
        f"Executing default use case (UC3) for asset_id: '{asset_id_to_use}'..."
    )
    try:
        # The uccontroller.executeUc3 expects 'asset_id_param' keyword argument.
        result = uc_controller.executeUc3(asset_id_param=asset_id_to_use)
        if result and not result.get("error"):
            logger.info(
                "Use case UC3 executed successfully! Created/verified EDC entities:"
            )
            for key, value in result.items():
                if key != "error":
                    logger.info(f"  {key}: {value}")
        elif result and result.get("error"):
            logger.error(
                f"Use case UC3 completed with errors for asset '{asset_id_to_use}'. Error: {result.get('error')}. Details: {result}"
            )
        else:
            logger.error(
                f"Use case UC3 execution failed or returned an unexpected result for asset '{asset_id_to_use}'."
            )
    except Exception as e:
        logger.exception(
            f"An unhandled error occurred during use case UC3 execution for asset '{asset_id_to_use}'."
        )


if __name__ == "__main__":
    main()

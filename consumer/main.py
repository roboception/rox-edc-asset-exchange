#!/usr/bin/env python3

import argparse
import os  # Ensure os is imported
import logging
from dotenv import load_dotenv
from .dataspace_client import DataspaceClient
from .uc_controller import UcController
from .config import settings  # Import the global settings

# Setup basic logging
# Logging level will be updated once settings are loaded
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_consumer_as_function(asset_id_param: str, env_file_param: str = None):
    """Runs the consumer logic as a function, allowing parameter passing."""
    logger.info(
        f"Running consumer as function. Asset ID: {asset_id_param}, Env File: {env_file_param}"
    )

    env_full_path_for_loading = None

    if env_file_param:
        env_full_path_for_loading = env_file_param
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env_full_path_for_loading = os.path.join(
            script_dir, "consumer.env"
        )  # Default to consumer.env

    logger.info(f"Loading environment from: {env_full_path_for_loading}")
    if os.path.exists(env_full_path_for_loading):
        load_dotenv(env_full_path_for_loading)
        settings.load_from_env()
    else:
        logger.warning(
            f"Environment file {env_full_path_for_loading} not found. Attempting to load from system environment."
        )
        settings.load_from_env()

    # Update logging level from settings
    logging.getLogger().setLevel(settings.LOG_LEVEL)
    logger.info(f"Logging configured to level: {settings.LOG_LEVEL}")

    logger.info(
        f"Using environment loaded from: {env_full_path_for_loading if os.path.exists(env_full_path_for_loading) else 'System Environment'}"
    )

    client = DataspaceClient()
    controller = UcController(client=client)

    asset_id_to_use = asset_id_param
    logger.info(f"Consumer process starting for asset ID: {asset_id_to_use}")

    os.makedirs(settings.ARTIFACT_DOWNLOAD_PATH, exist_ok=True)
    logger.info(f"Artifact download path set to: {settings.ARTIFACT_DOWNLOAD_PATH}")

    retrieved_file_path = controller.run_consumer_workflow(
        target_asset_id=asset_id_to_use
    )

    if retrieved_file_path:
        logger.info(
            f"Consumer workflow executed successfully. Data for asset '{asset_id_to_use}' downloaded to: {retrieved_file_path}"
        )
        return retrieved_file_path
    else:
        logger.error(f"Consumer workflow failed for asset '{asset_id_to_use}'.")
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Consumer application.")
    parser.add_argument(
        "asset_id",
        nargs="?",
        default=None,
        help="The Asset ID to be fetched. If not provided, available assets will be listed.",
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="Optional path to a .env file to load. Defaults to 'consumer.env' in the script directory if not provided.",
    )
    args = parser.parse_args()

    asset_id_to_use = args.asset_id
    env_file_to_load = args.env_file

    run_consumer_as_function(
        asset_id_param=asset_id_to_use, env_file_param=env_file_to_load
    )

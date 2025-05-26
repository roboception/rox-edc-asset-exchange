# Dataspace EDC Asset Exchange: A Practical Demonstration

This project provides a hands-on example of a secure and sovereign data exchange using **Eclipse Dataspace Connector (EDC)** components. It showcases a complete end-to-end workflow where a **Provider** makes a data asset available, and a **Consumer** discovers, negotiates access, and retrieves that asset. This is a fundamental pattern in building data spaces where organizations can share data under their own terms and control.

## The Big Picture: What is this Repository For?

Imagine two organizations that want to exchange data without losing control over it. This repository demonstrates how they can achieve this:

1.  **Provider's Role**:
    *   **Owns Data**: The Provider has a piece of data (e.g., a file in an S3 bucket) they are willing to share.
    *   **Defines Access Rules**: They don't want to give it away freely. Using their EDC, the Provider creates:
        *   An **Asset**: A digital representation of the data (e.g., "My Cool Dataset").
        *   A **Policy**: Rules that govern how the asset can be used (e.g., "Can only be used for non-commercial purposes," or "Access granted only to BPN XYZ").
        *   A **Contract Definition**: Links the asset to the policy, making it offerable to potential consumers.
    *   **Registers with EDC**: All these definitions are registered with the Provider's EDC instance, making the asset discoverable.

2.  **Consumer's Role**:
    *   **Needs Data**: The Consumer is interested in the data asset offered by the Provider.
    *   **Discovers the Asset**: The Consumer's EDC queries the Provider's EDC (via its public catalog) to find available assets.
    *   **Negotiates Access**: Once the desired asset is found, the Consumer's EDC initiates a contract negotiation with the Provider's EDC. This involves:
        *   The Consumer presenting its identity (e.g., its Business Partner Number - BPN).
        *   The Provider's EDC evaluating if the Consumer meets the policy requirements.
    *   **Receives an Endpoint Data Reference (EDR)**: If the negotiation is successful, the Provider's EDC issues an EDR. This EDR is a secure token that contains the actual information on how to access the data (e.g., temporary credentials for the S3 bucket).
    *   **Accesses Data**: The Consumer uses the EDR to directly access the data from its source (e.g., downloads the file from S3). The data transfer happens directly between the Consumer and the data source, not necessarily through the EDCs themselves after the EDR is issued.

3.  **EDC's Magic**:
    *   The EDC connectors on both sides handle the complex interactions of asset advertisement, policy enforcement, contract negotiation, and secure EDR exchange.
    *   This ensures that data is shared only according to the Provider's terms and that both parties have a trusted mechanism for interaction.

This repository provides Python scripts that automate these roles, allowing you to simulate this entire process locally or in a test environment.

## Core Concepts Explained

- **Provider (`provider/`)**:
    - Manages the creation and registration of data assets within its EDC.
    - Defines usage policies and contract definitions that govern access to these assets.
    - Interacts with an Object Storage system (like S3) where the actual data resides.
- **Consumer (`consumer/`)**:
    - Queries the Provider's EDC catalog to discover available data assets.
    - Initiates and manages contract negotiations for desired assets.
    - Once a contract is agreed and an EDR is received, it uses the EDR to fetch the data from the Provider's storage.
- **EDC Connector (Implicit)**:
    - While not explicitly part of this codebase (you'd run separate EDC instances), these scripts interact with the Management APIs of both the Provider's and Consumer's EDC connectors.
    - These connectors are the backbone, enabling sovereign data sharing through standardized dataspace protocols (e.g., IDS, Dataspace Protocol).
- **`.env` Files**:
    - Crucial for configuring the applications. They store:
        - EDC Management API endpoints (e.g., `http://localhost:19193/management`).
        - API keys for authenticating with the EDC Management APIs.
        - Business Partner Numbers (BPNs) for identifying the Provider and Consumer.
        - Details for connecting to object storage (e.g., S3 bucket names, regions, credentials).
        - Other environment-specific settings.
- **Endpoint Data Reference (EDR)**:
    - A key piece of information securely transferred from the Provider's EDC to the Consumer's EDC after a successful contract negotiation.
    - Contains the necessary details (e.g., endpoint URL, authorization token) for the Consumer to access the actual data asset directly from its storage location. The EDR is typically short-lived.

## Prerequisites

- Python 3.8+
- `pip` (Python package installer)
- `venv` (Python virtual environment tool, usually included with Python)
- **Two running EDC instances**: One configured as the Provider and one as the Consumer. This project *does not* include the EDC setup itself. You are expected to have these running and accessible.
    - You will need their respective Management API endpoints and API keys.

## Setup & Configuration

1.  **Clone the Repository**:
    ```bash
    git clone <repository_url> rox-edc-asset-exchange
    cd rox-edc-asset-exchange
    ```

2.  **Create and Activate a Virtual Environment**:
    It's highly recommended to use a virtual environment to manage project dependencies.
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    (On Windows, activation is typically `venv\\Scripts\\activate`)

3.  **Install Dependencies**:
    The project includes a `combined_requirements.txt` for convenience.
    ```bash
    pip install -r combined_requirements.txt
    ```

4.  **Configure Environment Files (`.env`)**:
    Template environment files (`provider.env.example` and `consumer.env.example`) are provided. **You must copy these and fill in your specific details.**

    *   **For the Provider**:
        ```bash
        cp provider/provider.env.example provider/provider.env
        ```
        Now, edit `provider/provider.env`. Key settings include:
        - `PROVIDER_EDC_BASE_URL`: Management API of the Provider's EDC.
        - `PROVIDER_EDC_API_KEY`: API key for the Provider's EDC.
        - `PROVIDER_BPN`: Business Partner Number of the Provider.
        - `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET_NAME`, `S3_REGION`: Details for the S3 bucket where the Provider's data is stored.

    *   **For the Consumer**:
        ```bash
        cp consumer/consumer.env.example consumer/consumer.env
        ```
        Edit `consumer/consumer.env`. Key settings include:
        - `CONSUMER_EDC_BASE_URL`: Management API of the Consumer's EDC.
        - `CONSUMER_EDC_API_KEY`: API key for the Consumer's EDC.
        - `CONSUMER_BPN`: Business Partner Number of the Consumer.
        - `PROVIDER_IDS_ENDPOINT`: IDS/DSP protocol endpoint of the Provider's EDC (used for discovery and negotiation).

    **Important Security Note**:
    Do **NOT** commit your actual `.env` files (containing sensitive credentials) to version control. The `.gitignore` file is configured to ignore `*.env` files, but always double-check.

## How to Run

### Provider Component

The Provider script (`provider/main.py`) is responsible for creating an asset, defining a policy for it, and creating a contract definition so it can be offered.

```bash
# Ensure your virtual environment is active and provider.env is correctly configured
cd provider

# Example: Create an asset with ID "my-test-asset-1"
python3 main.py my-test-asset-1

# To use a specific .env file:
# python3 main.py my-test-asset-1 --env-file /path/to/your/custom_provider.env
cd ..
```
-   `asset_id` (mandatory in this example): A unique identifier for the data asset you are creating.
-   `--env-file` (optional): Path to the provider's environment file. Defaults to `provider/provider.env`.

The script will interact with your Provider EDC's Management API to:
1.  Create an Asset entity.
2.  Create a Policy Definition (e.g., a simple "allow all" policy or a more restrictive one).
3.  Create a Contract Definition, linking the Asset to the Policy.

### Consumer Component

The Consumer script (`consumer/main.py`) attempts to discover the asset from the provider, negotiate a contract, and then (if successful) use the EDR to fetch data.

```bash
# Ensure your virtual environment is active and consumer.env is correctly configured
cd consumer

# Example: Consume the asset with ID "my-test-asset-1" from the configured Provider
python3 main.py my-test-asset-1

# To use a specific .env file:
# python3 main.py my-test-asset-1 --env-file /path/to/your/custom_consumer.env
cd ..
```
-   `asset_id` (mandatory in this example): The ID of the asset you want to consume (must match an asset created by the Provider).
-   `--env-file` (optional): Path to the consumer's environment file. Defaults to `consumer/consumer.env`.

The script will:
1.  Query the Provider's IDS/DSP endpoint to get its catalog of assets.
2.  Find the specified `asset_id`.
3.  Initiate a contract negotiation process.
4.  Poll for the EDR (Endpoint Data Reference).
5.  If an EDR is obtained, it will attempt to use it to fetch the data.

## End-to-End Test (`test_both.py`)

A script `test_both.py` is provided in the project root to demonstrate the full flow:

```bash
# Ensure your virtual environment is active and BOTH .env files are configured
python3 test_both.py
```

This script will:
1.  Prompt you to enter an `asset_id`.
2.  Run the **Provider script** (`provider/main.py`) to create and register this asset using `provider/provider.env`.
3.  Pause briefly (configurable in the script).
4.  Run the **Consumer script** (`consumer/main.py`) to discover, negotiate, and retrieve the asset using `consumer/consumer.env`.

This is the best way to quickly test if your EDC setup and environment configurations are working correctly for a basic data exchange.

## Key Files and Directory Structure

```
.
├── venv/                   # Python virtual environment (created by you, gitignored)
├── provider/
│   ├── main.py             # Main script to run the Provider logic
│   ├── uccontroller.py     # Use Case Controller: orchestrates provider actions
│   ├── edcmanager.py       # Handles interactions with the Provider's EDC Management API
│   ├── objectstoremanager.py # (If used) Manages interaction with S3/Object Storage
│   ├── config.py           # Loads configuration from .env file
│   ├── provider.env.example# Template for Provider configuration
│   ├── provider.env        # Your actual Provider config (GIT IGNORED)
│   └── requirements.txt    # Python dependencies for the Provider
├── consumer/
│   ├── main.py             # Main script to run the Consumer logic
│   ├── uc_controller.py    # Use Case Controller: orchestrates consumer actions
│   ├── dataspace_client.py # Handles interactions with Provider's IDS and Consumer's EDC API
│   ├── config.py           # Loads configuration from .env file
│   ├── consumer.env.example# Template for Consumer configuration
│   ├── consumer.env        # Your actual Consumer config (GIT IGNORED)
│   └── requirements.txt    # Python dependencies for the Consumer
├── test_both.py            # Script to run provider and consumer sequentially
├── combined_requirements.txt # All dependencies for easy installation
└── README.md               # This file
```

## Troubleshooting Common Issues

*   **EDR Polling Returns Empty `[]` or Times Out**:
    *   **Provider EDC Not Ready**: The Provider's EDC might not have fully processed the new asset, policy, and contract definition. Ensure there's enough time or a mechanism for the provider to confirm its readiness before the consumer tries to negotiate.
    *   **Policy Misconfiguration**: The policy defined by the Provider might be too restrictive, or the Consumer might not meet its criteria (e.g., incorrect BPN). Double-check policy definitions.
    *   **Contract Definition Issues**: Ensure the `assetsSelector` in the Contract Definition correctly targets the asset.
    *   **EDC Instance Problems**: Check logs of both Provider and Consumer EDC instances for errors during asset creation, policy definition, or contract negotiation.
    *   **Network Connectivity**: Ensure the Consumer's EDC can reach the Provider's IDS/DSP endpoint and vice-versa if needed for callbacks.
    *   **IDS/DSP Endpoint Configuration**: Verify that `PROVIDER_IDS_ENDPOINT` in `consumer.env` is correct and points to the Provider's protocol endpoint (not the management API).
*   **"Asset not found" errors**:
    *   Ensure the `asset_id` used by the consumer matches exactly the `asset_id` created by the provider.
    *   Check the Provider's EDC catalog (e.g., via its Management API or IDS/DSP endpoint) to see if the asset is listed.
*   **Authentication/Authorization Errors (401/403)**:
    *   Verify API keys (`PROVIDER_EDC_API_KEY`, `CONSUMER_EDC_API_KEY`) in your `.env` files are correct for the respective EDC Management APIs.
*   **S3/Data Access Errors (after EDR is received)**:
    *   Ensure the EDR contains valid credentials and endpoint for the S3 bucket.
    *   Check S3 bucket policies and CORS configurations if accessing from a browser or different origin.
    *   The temporary credentials in the EDR might have expired.

This repository serves as a starting point. Real-world data space interactions involve more complex policies, identity management, and trust frameworks.

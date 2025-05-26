
# Dataspace EDC Asset Exchange

This project demonstrates a basic end-to-end data exchange scenario using EDC (Eclipse Dataspace Connector) components. It includes a Provider application to register data and a Consumer application to retrieve it.

## Core Concepts

- **Provider**: Manages data assets, defines policies for their use, and registers them with its EDC connector.
- **Consumer**: Discovers assets from a provider's EDC connector, negotiates contracts, and accesses the data.
- **EDC Connector**: The central component enabling sovereign data sharing via dataspace protocols.
- **.env Files**: Used for configuring connector endpoints, API keys, BPNs, and other sensitive or environment-specific settings.

## Prerequisites

- Python 3.8+
- `pip` (Python package installer)
- `venv` (Python virtual environment tool, usually included with Python)

## Setup & Configuration

1.  **Clone the Repository** (if you haven't already):
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
    On Windows, activation is typically `venv\Scripts\activate`.

3.  **Install Dependencies**:
    Each component (`provider`, `consumer`) has its own `requirements.txt`. The combined requirements are within combined_requirements.txt
    ```bash
    pip install -r combined_requirements.txt
    ```



4.  **Configure Environment Files**:
    Template environment files (`.env.example`) are provided in both the `provider` and `consumer` directories. You'll need to copy these and fill in your specific details.

    *   **For the Provider**:
        ```bash
        cp provider/provider.env.example provider/provider.env
        ```
        Now, edit `provider/provider.env` and replace the placeholder values with your actual configuration.

    *   **For the Consumer**:
        ```bash
        cp consumer/consumer.env.example consumer/consumer.env
        ```
        Edit `consumer/consumer.env` and replace placeholders with your actual configuration.

    **Important**: Do NOT commit your actual `.env` files with sensitive credentials to version control. The `.gitignore` file should be configured to ignore `*.env`.

## Provider Component

Navigate to the provider directory and run `main.py`:

```bash
# Ensure your virtual environment is active and provider.env is configured
cd provider
python3 main.py [asset_id] [--env-file path/to/your/provider.env]
```

-   `asset_id` (optional): ...
-   `--env-file` (optional): ... Defaults to `provider.env` in the `provider` directory.

## Consumer Component

Navigate to the consumer directory and run `main.py`:

```bash
# Ensure your virtual environment is active and consumer.env is configured
cd consumer
python3 main.py [asset_id] [--env-file path/to/your/consumer.env]
```

-   `asset_id` (optional): ...
-   `--env-file` (optional): ... Defaults to `consumer.env` in the `consumer` directory.

## Example Workflow (`test_both.py`)

A script `test_both.py` is provided in the project root to demonstrate an end-to-end flow once everything is configured:

```bash
# Ensure your virtual environment is active and .env files are configured
python3 test_both.py
```

This script will:
1. Prompt for an `asset_id`.
2. Run the provider to create and register the asset (using `provider/provider.env`).
3. Run the consumer to retrieve the asset (using `consumer/consumer.env`).

## Key Files Structure (Simplified)

```
.
├── venv/                   # Python virtual environment (created by you)
├── provider/
│   ├── main.py
│   ├── uccontroller.py
│   ├── edcmanager.py
│   ├── objectstoremanager.py
│   ├── config.py
│   ├── provider.env.example  # Template (copy to provider.env and fill)
│   ├── provider.env          # Your actual config (GIT IGNORED)
│   └── requirements.txt
├── consumer/
│   ├── main.py
│   ├── uc_controller.py
│   ├── dataspace_client.py
│   ├── config.py
│   ├── consumer.env.example  # Template (copy to consumer.env and fill)
│   ├── consumer.env          # Your actual config (GIT IGNORED)
│   └── requirements.txt
├── test_both.py
└── README.md
```

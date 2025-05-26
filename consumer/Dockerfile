FROM python:3.9-slim

# Install required packages
RUN apt-get update && apt-get install -y curl jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the rest of the application
COPY . .

# Set the entrypoint to the Python script
ENTRYPOINT ["python"]
CMD ["request_flow.py"]
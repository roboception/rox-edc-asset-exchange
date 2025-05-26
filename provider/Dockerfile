# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app/provider

# Install system dependencies that might be needed by some python packages
# (e.g., for Pillow, lxml, etc. - good to have a placeholder if needed later)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     # Add any system dependencies here if required, e.g., build-essential libpq-dev
#  && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app/provider
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the provider application code into the container at /app/provider
# This includes provider_app.py, all manager .py files, templates/, .env files etc.
COPY . .

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Define environment variables (can be overridden at runtime)
# For example, you might want to set a default environment file for the Flask app to load
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=provider_app.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5001

# The command to run when the container launches
# Using `flask run` is good for development, but for production, a proper WSGI server like Gunicorn is recommended.
# For this exercise, `python provider_app.py` is fine as it has app.run() configured.
CMD ["python", "provider_app.py"] 
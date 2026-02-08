# Use the official Python 3.12 image as the base image
FROM python:3.12-slim

# Install required system packages for building Python wheels
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    libffi-dev \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the rest of your application code into the container
COPY . .

# Expose the application port (optional, depends on your app)
EXPOSE 8000

# Run the shell script as the container's command
CMD ["bash", "/app/scripts/setup.sh"]

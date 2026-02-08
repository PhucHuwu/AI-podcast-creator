#!/bin/bash

set -e  # Exit on any error

echo "Checking Python virtual environment..."

# Function to verify if 'venv' is a valid environment
is_valid_venv() {
    [ -d "venv" ] && [ -x "venv/bin/activate" ] && venv/bin/python -m ensurepip > /dev/null 2>&1
}

if is_valid_venv; then
    echo "Using existing virtual environment..."
else
    echo "Virtual environment not found or broken. Creating a new one..."
    python3 -m venv venv
fi

# Activate the environment
source venv/bin/activate

echo "Installing/updating dependencies..."
pip3 install --upgrade pip
pip3 install --upgrade -r requirements.txt

# Run your app
echo "Starting the Python application..."
python3 server.py

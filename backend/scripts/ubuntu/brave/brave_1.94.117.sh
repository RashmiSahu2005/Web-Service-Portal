#!/bin/bash

# Set the DEBIAN_FRONTEND to noninteractive
export DEBIAN_FRONTEND=noninteractive

# Check if brave is already installed
if command -v brave-browser &> /dev/null; then
    echo "Brave is already installed."
    exit 0
fi

# Install brave repository
echo "Adding brave repository..."
curl -s https://brave-browser-apt-release.s3.brave.com/brave-core.asc | apt-key adv --keyserver keyserver.ubuntu.com --recv-keys
echo "deb [arch=amd64] https://brave-browser-apt-release.s3.brave.com/ stable main" | tee /etc/apt/sources.list.d/brave-browser-release.list

# Update package list
echo "Updating package list..."
apt-get update

# Install brave-browser
echo "Installing brave-browser..."
apt-get install -y brave-browser=1.94.117

# Verify installation
if command -v brave-browser &> /dev/null; then
    echo "Brave installation successful."
    version=$(brave-browser --version)
    echo "Brave version: $version"
else
    echo "Brave installation failed."
    exit 1
fi

# Print deployiq result
echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=brave"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=$version"
echo "DEPLOYIQ_RESULT_END"
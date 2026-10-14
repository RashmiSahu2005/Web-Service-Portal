# Set DEBIAN_FRONTEND to noninteractive to avoid prompts
export DEBIAN_FRONTEND=noninteractive

# Define the package name and version
PACKAGE_NAME="nmap"
TARGET_VERSION="7.91"

# Check if the package is already installed
if dpkg -l | grep -q "ii  $PACKAGE_NAME"; then
    CURRENT_VERSION=$(dpkg-query -W -f='${Version}\n' "$PACKAGE_NAME" 2>/dev/null)
    if [[ "$CURRENT_VERSION" == "$TARGET_VERSION" ]]; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Nmap"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$CURRENT_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    else
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Nmap"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=VERSION_MISMATCH"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

# Update the package list
sudo apt-get update >"/var/tmp/apt_update.log" 2>&1; UPDATE_EXIT=$?

# Check for network or DNS failure
if [[ $UPDATE_EXIT -ne 0 ]]; then
    if echo "$(/var/tmp/apt_update.log)" | grep -q "Failed to fetch.*404 Not Found"; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Nmap"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    elif echo "$(/var/tmp/apt_update.log)" | grep -q "Failed to fetch.*Temporary failure in name resolution"; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Nmap"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=DNS_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

# Install the package
sudo apt-get install -y "$PACKAGE_NAME"

# Verify the installation
if test -f '/usr/bin/nmap'; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Nmap"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$(dpkg-query -W -f='${Version}\n' "$PACKAGE_NAME")"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Nmap"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=VERIFICATION_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi
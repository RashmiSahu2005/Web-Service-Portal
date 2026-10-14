set -o pipefail

DEBIAN_FRONTEND=noninteractive

# Check if flameshot is already installed
if dpkg -l | grep -q "^ii  flameshot"; then
    CURRENT_VERSION=$(dpkg-query -W -f='${Version}\n' flameshot 2>/dev/null)
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Flameshot"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS_VERSION_MISMATCH"
    echo "INSTALLED_VERSION=$CURRENT_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

# Update package list
sudo apt-get update >"/var/tmp/apt_update.log" 2>&1; UPDATE_EXIT=$?
if [ $UPDATE_EXIT -ne 0 ]; then
    if echo "$(/var/tmp/apt_update.log)" | grep -q "Temporary failure in name resolution"; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Flameshot"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=DNS_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    elif echo "$(/var/tmp/apt_update.log)" | grep -q "Could not resolve"; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Flameshot"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    else
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=Flameshot"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=APT_REPOSITORY_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

# Install flameshot
sudo apt-get install flameshot -y >"/var/tmp/flameshot_install.log" 2>&1; INSTALL_EXIT=$?
if [ $INSTALL_EXIT -ne 0 ]; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Flameshot"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

# Verify installation
if ! which flameshot > /dev/null; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=Flameshot"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=EXECUTION_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

# Get installed version
INSTALLED_VERSION=$(dpkg-query -W -f='${Version}\n' flameshot 2>/dev/null)
echo "DEPLOYIQ_RESULT_START"
echo "APPLICATION=Flameshot"
echo "INSTALLATION_STATUS=SUCCESS"
echo "VERIFICATION_STATUS=SUCCESS"
echo "INSTALLED_VERSION=$INSTALLED_VERSION"
echo "DEPLOYIQ_RESULT_END"
exit 0
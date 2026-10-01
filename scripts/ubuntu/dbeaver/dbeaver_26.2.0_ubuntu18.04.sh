set -e

echo "Checking if dbeaver-ce is already installed..."
if dpkg-query -W -f='${Status}' dbeaver-ce 2>/dev/null | grep -q "ok installed"; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' dbeaver-ce)
    echo "DBeaver CE is already installed. Version: $INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=DBeaver"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "Preparing system for installation..."
export DEBIAN_FRONTEND=noninteractive

# To prevent the script from failing due to unrelated broken third-party repositories 
# (like the MySQL or Microsoft errors seen in previous attempts), we ensure the 
# local cache is updated but we do not let a general 'apt-get update' kill the process
# if other unrelated repos are unsigned. However, we must update to fetch the PPA.

echo "Adding DBeaver CE PPA..."
# add-apt-repository handles the GPG key import automatically
if ! apt-get update -y; then
    echo "Warning: apt-get update encountered errors with some repositories. Attempting to proceed with PPA addition..."
fi

if ! apt-add-repository -y ppa:serge-rider/dbeaver-ce; then
    echo "FATAL: Failed to add PPA"
    exit 1
fi

echo "Updating package lists specifically for the new PPA..."
# We use -o Dir::Etc::sourcelist to focus or just ignore unrelated errors for the specific install
apt-get update -y || echo "Continuing despite some repository errors..."

echo "Installing dbeaver-ce..."
if ! apt-get install -y dbeaver-ce; then
    echo "FATAL: Installation of dbeaver-ce failed"
    exit 1
fi

echo "Verifying installation..."
if dpkg-query -W -f='${Status}' dbeaver-ce 2>/dev/null | grep -q "ok installed"; then
    ACTUAL_VERSION=$(dpkg-query -W -f='${Version}' dbeaver-ce)
    echo "Verification successful. Installed version: $ACTUAL_VERSION"
    
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=DBeaver"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$ACTUAL_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "FATAL: Verification failed. Package not found after installation."
    exit 1
fi
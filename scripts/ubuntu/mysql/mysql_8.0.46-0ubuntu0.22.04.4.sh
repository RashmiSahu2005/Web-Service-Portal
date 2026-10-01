set -e

echo "Checking if mysql-server is already installed..."
if dpkg-query -W -f='${Status}' mysql-server 2>/dev/null | grep -q "ok installed"; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' mysql-server)
    echo "MySQL is already installed: $INSTALLED_VERSION"
    
    if service mysql status > /dev/null 2>&1; then
        echo "MySQL service is running."
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=MySQL"
        echo "INSTALLATION_STATUS=SUCCESS"
        echo "VERIFICATION_STATUS=SUCCESS"
        echo "INSTALLED_VERSION=$INSTALLED_VERSION"
        echo "DEPLOYIQ_RESULT_END"
        exit 0
    fi
fi

echo "Installing mysql-server..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y mysql-server

echo "Verifying installation..."
if ! dpkg-query -W -f='${Status}' mysql-server 2>/dev/null | grep -q "ok installed"; then
    echo "ERROR: mysql-server package not installed."
    exit 1
fi

if [ ! -f /usr/bin/mysql ]; then
    echo "ERROR: Executable /usr/bin/mysql not found."
    exit 1
fi

if ! service mysql status > /dev/null 2>&1; then
    echo "Attempting to start MySQL service..."
    service mysql start || { echo "ERROR: Failed to start MySQL service"; exit 1; }
fi

# Final Verification
if service mysql status > /dev/null 2>&1; then
    INSTALLED_VERSION=$(dpkg-query -W -f='${Version}' mysql-server)
    echo "MySQL installation verified successfully."
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=MySQL"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INSTALLED_VERSION"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "ERROR: MySQL service verification failed."
    exit 1
fi
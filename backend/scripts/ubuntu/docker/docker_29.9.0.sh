# Application configuration
APP_NAME="docker"
PKG_NAME="docker-ce"
VERIFY_CMD="docker --version"

# Idempotency check
if command -v docker >/dev/null 2>&1; then
    CURRENT_VER=$(docker --version)
    echo "Docker is already installed: $CURRENT_VER"
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$(dpkg-query -W -f='\${Version}\n' $PKG_NAME 2>/dev/null || echo "$CURRENT_VER")"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

# Set non-interactive frontend
export DEBIAN_FRONTEND=noninteractive

echo "Starting installation of $APP_NAME..."

# Step 1: Basic requirements
apt-get update >/var/tmp/apt_update_init.log 2>&1
UPDATE_EXIT=$?
if [ $UPDATE_EXIT -ne 0 ]; then
    if grep -qiE "Temporary failure in name resolution|Could not resolve host" /var/tmp/apt_update_init.log; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=DNS_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    elif grep -qiE "Failed to fetch|Network is unreachable" /var/tmp/apt_update_init.log; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

apt-get install -y ca-certificates curl >/var/tmp/apt_deps.log 2>&1
if [ $? -ne 0 ]; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

# Step 2: GPG Key and Repository setup
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc >/var/tmp/curl_gpg.log 2>&1
if [ $? -ne 0 ]; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=DOWNLOAD_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi
chmod a+r /etc/apt/keyrings/docker.asc

# Setup Docker source list
tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "\${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

# Step 3: Final Update and Installation
apt-get update >/var/tmp/apt_update_final.log 2>&1
UPDATE_EXIT=$?
if [ $UPDATE_EXIT -ne 0 ]; then
    # Fail only if network/DNS issues. Ignore GPG errors for unrelated repos.
    if grep -qiE "Temporary failure in name resolution|Could not resolve host" /var/tmp/apt_update_final.log; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=DNS_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    elif grep -qiE "Failed to fetch|Network is unreachable" /var/tmp/apt_update_final.log; then
        echo "DEPLOYIQ_RESULT_START"
        echo "APPLICATION=$APP_NAME"
        echo "INSTALLATION_STATUS=FAILED"
        echo "DEPLOYIQ_FAILURE_CATEGORY=NETWORK_FAILURE"
        echo "DEPLOYIQ_RESULT_END"
        exit 1
    fi
fi

apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/var/tmp/docker_install.log 2>&1
if [ $? -ne 0 ]; then
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=PACKAGE_MANAGER_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

# Step 4: Verification
if $VERIFY_CMD >/dev/null 2>&1; then
    INST_VER=$(dpkg-query -W -f='${Version}\n' $PKG_NAME 2>/dev/null || $VERIFY_CMD)
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INST_VER"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
else
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=FAILED"
    echo "DEPLOYIQ_FAILURE_CATEGORY=VERIFICATION_FAILURE"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi
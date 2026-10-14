#!/bin/bash
set -e

APP_NAME="wazuh-agent"
MANAGER_IP="192.168.0.129"

echo "=== Checking existing Wazuh installation ==="
if dpkg -s wazuh-agent >/dev/null 2>&1; then
    INST_VER=$(dpkg-query -W -f='${Version}' wazuh-agent)
    echo "Wazuh agent is already installed: $INST_VER"
    systemctl restart wazuh-agent || true
    echo "DEPLOYIQ_RESULT_START"
    echo "APPLICATION=$APP_NAME"
    echo "INSTALLATION_STATUS=SUCCESS"
    echo "VERIFICATION_STATUS=SUCCESS"
    echo "INSTALLED_VERSION=$INST_VER"
    echo "DEPLOYIQ_RESULT_END"
    exit 0
fi

echo "=== Installing Wazuh Agent for Manager $MANAGER_IP ==="
export DEBIAN_FRONTEND=noninteractive

# Step 1: Install prerequisite curl & gpg
apt-get update -y
apt-get install -y curl apt-transport-https gnupg

# Step 2: GPG Key
install -m 0755 -d /usr/share/keyrings
curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | gpg --no-default-keyring --keyring gnupg-ring:/usr/share/keyrings/wazuh.gpg --import
chmod 644 /usr/share/keyrings/wazuh.gpg

# Step 3: Add repo
echo "deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main" | tee /etc/apt/sources.list.d/wazuh.list

# Step 4: Update & install agent
apt-get update -y
WAZUH_MANAGER="$MANAGER_IP" apt-get install -y wazuh-agent

# Step 5: Configure manager if not set
sed -i "s/<address>.*<\/address>/<address>$MANAGER_IP<\/address>/g" /var/ossec/etc/ossec.conf

# Step 6: Enable and restart
systemctl daemon-reload
systemctl enable wazuh-agent
systemctl restart wazuh-agent

# Step 7: Verification
if dpkg -s wazuh-agent >/dev/null 2>&1; then
    INST_VER=$(dpkg-query -W -f='${Version}' wazuh-agent)
    echo "Wazuh Agent installed successfully: $INST_VER"
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
    echo "INSTALLATION_STATUS=FAILED"
    echo "VERIFICATION_STATUS=FAILED"
    echo "DEPLOYIQ_RESULT_END"
    exit 1
fi

const axios = require('axios');

const payload = {
    name: 'Visual Studio Code',
    version: '1.124.2',
    category: 'Development',
    description: '',
    package_name: 'code_1.124.2_amd64.deb',
    package_path: 'repository/visualstudiocode/code_1.124.2_amd64.deb',
    installer_type: 'deb',
    install_command: 'sudo dpkg -i {package}',
    minimum_battery_percentage: '30',
    retry_limit: '3',
    email_notification: true,
    auto_remediation: true,
    status: 'ACTIVE'
};

axios.post('http://localhost:8000/admin/applications', payload)
    .then(res => console.log("Success:", res.data))
    .catch(err => {
        console.error("Error:", err.response ? err.response.data : err.message);
    });

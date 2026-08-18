import axios from 'axios';

// Create an Axios instance with base URL pointing to the FastAPI backend
const apiClient = axios.create({
  baseURL: 'http://192.168.10.83:8000',
  headers: {
    'Content-Type': 'application/json'
  }
});

// Applications API
export const getApplications = async () => {
  try {
    const response = await apiClient.get('/applications');
    return response.data;
  } catch (error) {
    console.error("Error fetching applications:", error);
    throw error;
  }
};

export const getAdminApplications = async () => {
  try {
    const response = await apiClient.get('/admin/applications');
    return response.data;
  } catch (error) {
    console.error("Error fetching admin applications:", error);
    throw error;
  }
};

export const createApplication = async (appData) => {
  try {
    const response = await apiClient.post('/admin/applications', appData);
    return response.data;
  } catch (error) {
    console.error("Error creating application:", error);
    throw error;
  }
};

export const updateApplication = async (appId, appData) => {
  try {
    const response = await apiClient.put(`/admin/applications/${appId}`, appData);
    return response.data;
  } catch (error) {
    console.error("Error updating application:", error);
    throw error;
  }
};

export const deleteApplication = async (appId) => {
  try {
    const response = await apiClient.delete(`/admin/applications/${appId}`);
    return response.data;
  } catch (error) {
    console.error("Error deleting application:", error);
    throw error;
  }
};

// Installation API
export const installApplication = async (applicationId) => {
  try {
    const response = await apiClient.post(`/install/${applicationId}`);
    return response.data; // Should return { installation_id: "..." }
  } catch (error) {
    console.error("Error requesting installation:", error);
    throw error;
  }
};

export const identifyHost = async (ipAddress) => {
  try {
    const response = await apiClient.post(`/hosts/identify`, { ip_address: ipAddress });
    return response.data;
  } catch (error) {
    console.error("Error identifying host:", error);
    throw error;
  }
};

export const startInstallation = async (jobId, payload = {}) => {
  try {
    const response = await apiClient.post(`/install/${jobId}/start`, payload);
    return response.data;
  } catch (error) {
    console.error("Error starting installation:", error);
    throw error;
  }
};

export const cancelInstallation = async (jobId) => {
  try {
    const response = await apiClient.post(`/install/${jobId}/cancel`);
    return response.data;
  } catch (error) {
    console.error("Error cancelling installation:", error);
    throw error;
  }
};

export const getInstallationStatus = async (installationId) => {
  try {
    const response = await apiClient.get(`/install/${installationId}`);
    return response.data;
  } catch (error) {
    console.error("Error getting installation status:", error);
    throw error;
  }
};

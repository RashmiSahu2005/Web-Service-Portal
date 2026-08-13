import React, { useState, useEffect } from 'react';
import { getAdminApplications, deleteApplication } from '../../services/api';
import { Plus, MoreVertical, Edit2, Trash2, Eye, AlertTriangle } from 'lucide-react';
import AddApplicationModal from '../../components/AddApplicationModal/AddApplicationModal.jsx';

const AdminDashboard = () => {
  const [applications, setApplications] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalMode, setModalMode] = useState('add'); // 'add', 'edit', 'view'
  const [selectedApp, setSelectedApp] = useState(null);
  
  const [deleteDialogState, setDeleteDialogState] = useState({ isOpen: false, app: null });
  const [toastMessage, setToastMessage] = useState('');

  useEffect(() => {
    const fetchApps = async () => {
      try {
        const data = await getAdminApplications();
        setApplications(data);
      } catch (error) {
        console.error("Failed to fetch applications for admin:", error);
      }
    };
    fetchApps();
  }, []);

  const handleOpenModal = (mode, app = null) => {
    setModalMode(mode);
    setSelectedApp(app);
    setIsModalOpen(true);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteDialogState.app) return;
    try {
      await deleteApplication(deleteDialogState.app.id);
      const data = await getAdminApplications();
      setApplications(data);
      setToastMessage('Application deleted successfully.');
      setTimeout(() => setToastMessage(''), 3000);
    } catch (error) {
      console.error("Failed to delete application:", error);
      alert("Failed to delete application: " + error.message);
    } finally {
      setDeleteDialogState({ isOpen: false, app: null });
    }
  };

  const stats = [
    { label: 'Total Applications', value: applications.length.toString() },
    { label: 'Pending Requests', value: '12' },
    { label: 'Completed Today', value: '45' },
    { label: 'Failed', value: '2' },
  ];

  return (
    <div className="space-y-8">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Admin Dashboard</h1>
          <p className="text-gray-500">Manage catalog and view statistics</p>
        </div>
        <button 
          onClick={() => handleOpenModal('add')}
          className="flex items-center px-4 py-2 bg-[#004aad] hover:bg-[#003882] text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
        >
          <Plus className="w-4 h-4 mr-2" />
          Add Application
        </button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        {stats.map(stat => (
          <div key={stat.label} className="bg-white border border-gray-200 p-6 rounded-2xl shadow-sm">
            <p className="text-gray-500 text-sm font-medium mb-2">{stat.label}</p>
            <h3 className="text-3xl font-bold text-gray-900">{stat.value}</h3>
          </div>
        ))}
      </div>

      {/* Table */}
      <div className="bg-white border border-gray-200 rounded-2xl overflow-hidden shadow-sm">
        <div className="px-6 py-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Application Catalog</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Application</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Version</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Category</th>
                <th className="px-6 py-4 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {applications.map(app => (
                <tr key={app.id} className="hover:bg-gray-50 transition-colors">
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center">
                      <div className="w-8 h-8 rounded bg-gray-100 border border-gray-200 flex items-center justify-center mr-3 overflow-hidden">
                        {app.package_path && app.package_path.startsWith('data:image') ? (
                          <img src={app.package_path} alt={app.name} className="w-full h-full object-cover" />
                        ) : (
                          <span className="text-xs font-bold text-gray-600">{app.name.substring(0,2).toUpperCase()}</span>
                        )}
                      </div>
                      <div>
                        <div className="text-sm font-medium text-gray-900">{app.name}</div>
                        <div className="text-xs text-gray-500">{app.publisher}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-600 rounded border border-gray-200">
                      {app.version}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                    {app.category}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <span className="px-2.5 py-1 text-xs font-medium bg-green-100 text-green-700 rounded-full border border-green-200">
                      {app.status || 'Active'}
                    </span>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex justify-end space-x-2">
                      <button onClick={() => handleOpenModal('view', app)} className="p-1.5 text-gray-400 hover:text-gray-900 transition-colors rounded hover:bg-gray-100">
                        <Eye className="w-4 h-4" />
                      </button>
                      <button onClick={() => handleOpenModal('edit', app)} className="p-1.5 text-gray-400 hover:text-[#004aad] transition-colors rounded hover:bg-gray-100">
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button onClick={() => setDeleteDialogState({ isOpen: true, app })} className="p-1.5 text-gray-400 hover:text-red-600 transition-colors rounded hover:bg-red-50">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <AddApplicationModal 
        isOpen={isModalOpen} 
        mode={modalMode}
        initialData={selectedApp}
        onClose={() => {
          setIsModalOpen(false);
          setTimeout(() => setSelectedApp(null), 200); // Clear after animation
        }} 
        onSuccess={(mode) => {
          getAdminApplications().then(setApplications).catch(console.error);
          setToastMessage(mode === 'edit' ? 'Application updated successfully.' : 'Application added successfully.');
          setTimeout(() => setToastMessage(''), 3000);
        }} 
      />
      
      {/* Delete Confirmation Dialog */}
      {deleteDialogState.isOpen && (
        <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-sm rounded-2xl overflow-hidden shadow-2xl border border-gray-200 flex flex-col p-6">
            <div className="flex items-center space-x-3 mb-4">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center shrink-0">
                <AlertTriangle className="w-5 h-5 text-red-600" />
              </div>
              <h3 className="text-xl font-bold text-gray-900">Delete Application</h3>
            </div>
            <p className="text-sm text-gray-600 mb-6">
              Are you sure you want to delete <span className="font-semibold text-gray-900">'{deleteDialogState.app?.name}'</span>? This action cannot be undone.
            </p>
            <div className="flex justify-end space-x-3">
              <button onClick={() => setDeleteDialogState({ isOpen: false, app: null })} className="px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                Cancel
              </button>
              <button onClick={handleDeleteConfirm} className="px-4 py-2 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg transition-colors">
                Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 bg-gray-900 text-white px-6 py-3 rounded-lg shadow-lg flex items-center z-50 animate-fade-in-up">
          <div className="w-2 h-2 rounded-full bg-green-400 mr-3"></div>
          <span className="font-medium text-sm">{toastMessage}</span>
        </div>
      )}
    </div>
  );
};

export default AdminDashboard;

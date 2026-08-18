import React, { useState, useEffect } from 'react';
import { UploadCloud, X, File, Settings, HardDrive, Mail, Activity } from 'lucide-react';
import { createApplication, updateApplication } from '../../services/api';

const AddApplicationModal = ({ isOpen, onClose, onSuccess, mode = 'add', initialData = null }) => {
  const [formData, setFormData] = useState({
    name: '',
    version: '',
    category: '',
    description: '',
    fleet_script_id: '',
    minimum_battery_percentage: 30,
    retry_limit: 3,
    email_notification: true,
    auto_remediation: true,
  });

  useEffect(() => {
    if (isOpen) {
      if ((mode === 'edit' || mode === 'view') && initialData) {
        setFormData({
          name: initialData.name || '',
          version: initialData.version || '',
          category: initialData.category || '',
          description: initialData.description || '',
          package_name: initialData.package_name || '',
          package_path: initialData.package_path || '',
          installer_type: initialData.installer_type || '',
          install_command: initialData.install_command || '',
          fleet_script_id: initialData.fleet_script_id || '',
          minimum_battery_percentage: initialData.minimum_battery_percentage ?? 30,
          retry_limit: initialData.retry_limit ?? 3,
          email_notification: initialData.email_notification ?? true,
          auto_remediation: initialData.auto_remediation ?? true,
        });
      } else {
        setFormData({
          name: '',
          version: '',
          category: '',
          description: '',
          package_name: '',
          package_path: '',
          installer_type: '',
          install_command: '',
          fleet_script_id: '',
          minimum_battery_percentage: 30,
          retry_limit: 3,
          email_notification: true,
          auto_remediation: true,
        });
      }
    }
  }, [isOpen, mode, initialData]);

  if (!isOpen) return null;

  const isReadOnly = mode === 'view';

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? checked : value
    }));
  };

  const handleImageUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setFormData(prev => ({ ...prev, package_path: reader.result }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSave = async () => {
    if (!formData.name || !formData.category) {
      alert('Please fill out all required fields: Name, Category.');
      return;
    }
    
    if (formData.fleet_script_id) {
      if (!/^\d+$/.test(String(formData.fleet_script_id))) {
        alert('Fleet Script ID must be a positive integer.');
        return;
      }
    }

    try {
      const payload = {
        ...formData,
        minimum_battery_percentage: parseInt(formData.minimum_battery_percentage, 10) || 0,
        retry_limit: parseInt(formData.retry_limit, 10) || 0,
        status: initialData?.status || "ACTIVE"
      };
      
      if (mode === 'edit') {
        await updateApplication(initialData.id, payload);
      } else {
        await createApplication(payload);
      }
      
      onSuccess(mode);
      onClose();
    } catch (error) {
      alert(`Failed to ${mode === 'edit' ? 'update' : 'save'} application: ` + (error.response?.data?.detail?.[0]?.msg || error.message));
      console.error(`Failed to ${mode === 'edit' ? 'update' : 'create'} application`, error);
    }
  };

  return (
    <div className="fixed inset-0 bg-gray-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-white w-full max-w-2xl max-h-[90vh] rounded-2xl overflow-hidden shadow-2xl border border-gray-200 flex flex-col">
        
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
          <div className="flex items-center space-x-2">
            <div className="w-8 h-8 rounded bg-blue-50 flex items-center justify-center border border-blue-100">
              <HardDrive className="w-4 h-4 text-[#004aad]" />
            </div>
            <h3 className="text-xl font-bold text-gray-900">
              {mode === 'edit' ? 'Edit Application' : mode === 'view' ? 'View Application' : 'Add Application'}
            </h3>
          </div>
          <button onClick={onClose} className="p-2 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100 transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* Scrollable Content */}
        <div className="p-6 overflow-y-auto flex-1 space-y-8 custom-scrollbar">
          
          {/* Basic Info */}
          <div className="space-y-4">
            <div className="flex justify-between items-center">
              <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center">
                <Settings className="w-4 h-4 mr-2 text-gray-400" /> Basic Information
              </h4>
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 rounded bg-gray-100 border border-gray-200 flex items-center justify-center overflow-hidden">
                  {formData.package_path && formData.package_path.startsWith('data:image') ? (
                    <img src={formData.package_path} alt="Icon" className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-xs font-bold text-gray-600">
                      {formData.name ? formData.name.substring(0,2).toUpperCase() : 'APP'}
                    </span>
                  )}
                </div>
                {!isReadOnly && (
                  <label className="cursor-pointer px-3 py-1.5 bg-white border border-gray-200 hover:bg-gray-50 text-xs font-medium text-gray-700 rounded-lg transition-colors">
                    Upload Icon
                    <input type="file" className="hidden" accept="image/*" onChange={handleImageUpload} />
                  </label>
                )}
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Application Name *</label>
                <input readOnly={isReadOnly} required type="text" name="name" value={formData.name} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} placeholder="e.g. Visual Studio Code" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Version</label>
                <input readOnly={isReadOnly} type="text" name="version" value={formData.version} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} placeholder="latest or e.g. 138.0.7204.92" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Category *</label>
                <input readOnly={isReadOnly} required type="text" name="category" value={formData.category} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} placeholder="e.g. Development" />
              </div>
              <div className="col-span-2">
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea readOnly={isReadOnly} name="description" value={formData.description} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all h-20 resize-none`} placeholder="Short description of the application..."></textarea>
              </div>
            </div>
          </div>

          <hr className="border-gray-100" />

          {/* FleetDM Settings */}
          <div className="space-y-4">
            <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center">
              <HardDrive className="w-4 h-4 mr-2 text-gray-400" /> FleetDM Configuration
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Fleet Script ID</label>
                <input readOnly={isReadOnly} type="text" name="fleet_script_id" value={formData.fleet_script_id} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} placeholder="e.g. 161" />
                <p className="text-xs text-gray-500 mt-1">Required if FleetDM is enabled.</p>
              </div>
            </div>
          </div>

          <hr className="border-gray-100" />

          {/* Installation Policy */}
          <div className="space-y-4">
            <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center">
              <Activity className="w-4 h-4 mr-2 text-gray-400" /> Installation Policy
            </h4>
            <div className="grid grid-cols-2 gap-6">
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Minimum Battery (%)</label>
                  <input readOnly={isReadOnly} type="number" name="minimum_battery_percentage" value={formData.minimum_battery_percentage} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Max Retry Count</label>
                  <input readOnly={isReadOnly} type="number" name="retry_limit" value={formData.retry_limit} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} />
                </div>
              </div>
              <div className="space-y-4 bg-gray-50 p-4 rounded-xl border border-gray-100">
                <label className={`flex items-center space-x-3 ${isReadOnly ? 'opacity-70' : 'cursor-pointer'}`}>
                  <div className="relative">
                    <input disabled={isReadOnly} type="checkbox" name="auto_remediation" checked={formData.auto_remediation} onChange={handleChange} className="sr-only peer" />
                    <div className="w-10 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[#004aad]"></div>
                  </div>
                  <span className="text-sm font-medium text-gray-700">Enable Auto-Remediation</span>
                </label>
                <label className={`flex items-center space-x-3 ${isReadOnly ? 'opacity-70' : 'cursor-pointer'}`}>
                  <div className="relative">
                    <input disabled={isReadOnly} type="checkbox" name="email_notification" checked={formData.email_notification} onChange={handleChange} className="sr-only peer" />
                    <div className="w-10 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-[#004aad]"></div>
                  </div>
                  <span className="text-sm font-medium text-gray-700">Send Success Email</span>
                </label>
              </div>
            </div>
          </div>
          
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50/80 border-t border-gray-100 flex justify-end space-x-3">
          <button onClick={onClose} className="px-5 py-2.5 text-sm font-semibold text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors">
            {isReadOnly ? 'Close' : 'Cancel'}
          </button>
          {!isReadOnly && (
            <button onClick={handleSave} className="px-6 py-2.5 bg-[#004aad] hover:bg-[#003882] text-white text-sm font-semibold rounded-lg transition-colors shadow-sm">
              {mode === 'edit' ? 'Update Application' : 'Save Application'}
            </button>
          )}
        </div>

      </div>
    </div>
  );
};

export default AddApplicationModal;

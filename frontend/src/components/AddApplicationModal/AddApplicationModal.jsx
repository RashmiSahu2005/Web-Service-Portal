import React, { useState, useEffect } from 'react';
import { UploadCloud, X, File, Settings, HardDrive, Mail, Activity } from 'lucide-react';
import { createApplication, updateApplication } from '../../services/api';

const AddApplicationModal = ({ isOpen, onClose, onSuccess, mode = 'add', initialData = null }) => {
  const [formData, setFormData] = useState({
    name: '',
    version: '',
    category: '',
    description: '',
    package_name: '',
    package_path: '',
    installer_type: '',
    install_command: '',
    minimum_battery_percentage: 30,
    retry_limit: 3,
    email_notification: true,
    auto_remediation: true,
  });

  const [uploadStatus, setUploadStatus] = useState('idle'); // idle, uploading, done

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
          minimum_battery_percentage: initialData.minimum_battery_percentage ?? 30,
          retry_limit: initialData.retry_limit ?? 3,
          email_notification: initialData.email_notification ?? true,
          auto_remediation: initialData.auto_remediation ?? true,
        });
        if (initialData.package_name) {
          setUploadStatus('done');
        } else {
          setUploadStatus('idle');
        }
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
          minimum_battery_percentage: 30,
          retry_limit: 3,
          email_notification: true,
          auto_remediation: true,
        });
        setUploadStatus('idle');
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

  const handleFileDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer ? e.dataTransfer.files[0] : e.target.files[0];
    if (!file) return;

    setUploadStatus('uploading');
    
    // Simulate upload delay
    setTimeout(() => {
      const fileName = file.name;
      let installerType = 'unknown';
      let command = '';

      if (fileName.endsWith('.deb')) {
        installerType = 'deb';
        command = 'sudo dpkg -i {package}';
      } else if (fileName.endsWith('.rpm')) {
        installerType = 'rpm';
        command = 'sudo rpm -ivh {package}';
      } else if (fileName.endsWith('.AppImage')) {
        installerType = 'AppImage';
        command = 'chmod +x {package} && ./{package}';
      } else if (fileName.endsWith('.sh')) {
        installerType = 'sh';
        command = 'chmod +x {package} && ./{package}';
      } else if (fileName.endsWith('.tar.gz')) {
        installerType = 'tar.gz';
        command = 'tar -xzf {package}';
      }

      setFormData(prev => ({
        ...prev,
        package_name: fileName,
        package_path: `repository/${prev.name.toLowerCase().replace(/\\s+/g, '') || 'app'}/${fileName}`,
        installer_type: installerType !== 'unknown' ? installerType : prev.installer_type,
        install_command: command || prev.install_command,
      }));
      
      setUploadStatus('done');
    }, 1500);
  };

  const handleSave = async () => {
    // Validate required fields
    if (!formData.name || !formData.version || !formData.category) {
      alert('Please fill out all required fields: Name, Version, Category.');
      return;
    }
    if (!formData.package_name) {
      alert('Please upload a package first.');
      return;
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
            <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center">
              <Settings className="w-4 h-4 mr-2 text-gray-400" /> Basic Information
            </h4>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Application Name *</label>
                <input readOnly={isReadOnly} required type="text" name="name" value={formData.name} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} placeholder="e.g. Visual Studio Code" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Version *</label>
                <input readOnly={isReadOnly} required type="text" name="version" value={formData.version} onChange={handleChange} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all`} placeholder="e.g. 1.85.1" />
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

          {/* Package Upload */}
          <div className="space-y-4">
            <h4 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center">
              <UploadCloud className="w-4 h-4 mr-2 text-gray-400" /> Package Upload
            </h4>
            
            {uploadStatus === 'idle' && (
              <label 
                onDragOver={isReadOnly ? undefined : (e) => e.preventDefault()} 
                onDrop={isReadOnly ? undefined : handleFileDrop}
                className={`flex flex-col items-center justify-center w-full h-32 border-2 ${isReadOnly ? 'border-gray-200 bg-gray-50' : 'border-dashed border-blue-200 bg-blue-50/50 hover:bg-blue-50 cursor-pointer'} rounded-xl transition-colors group`}
              >
                <div className="flex flex-col items-center justify-center pt-5 pb-6">
                  <UploadCloud className={`w-8 h-8 ${isReadOnly ? 'text-gray-400' : 'text-blue-400 group-hover:scale-110 transition-transform'} mb-2`} />
                  <p className="mb-1 text-sm text-gray-600">
                    {isReadOnly ? 'No package uploaded' : <><span className="font-semibold text-[#004aad]">Click to upload</span> or drag and drop</>}
                  </p>
                  {!isReadOnly && <p className="text-xs text-gray-500">.deb, .rpm, .AppImage, .tar.gz, .sh</p>}
                </div>
                {!isReadOnly && <input type="file" className="hidden" onChange={handleFileDrop} />}
              </label>
            )}

            {uploadStatus === 'uploading' && (
              <div className="w-full h-32 border border-gray-200 rounded-xl bg-gray-50 flex items-center justify-center">
                 <div className="flex flex-col items-center">
                   <div className="w-6 h-6 border-2 border-[#004aad] border-t-transparent rounded-full animate-spin mb-2"></div>
                   <span className="text-sm text-gray-500 font-medium">Processing Package...</span>
                 </div>
              </div>
            )}

             {uploadStatus === 'done' && (
              <div className="w-full p-4 border border-green-200 rounded-xl bg-green-50 flex items-start space-x-4">
                 <div className="p-2 bg-green-100 rounded-lg">
                   <File className="w-6 h-6 text-green-600" />
                 </div>
                 <div className="flex-1 min-w-0">
                   <p className="text-sm font-bold text-gray-900 truncate">{formData.package_name}</p>
                   <p className="text-xs text-gray-500 truncate mb-2">{formData.package_path}</p>
                   <div className="flex space-x-4">
                     <div className="flex flex-col">
                       <span className="text-[10px] text-gray-400 uppercase font-bold">Auto-Detected Type</span>
                       <span className="text-xs font-medium text-gray-700 bg-white px-2 py-0.5 rounded border border-gray-200 mt-1 inline-block w-max">{formData.installer_type}</span>
                     </div>
                   </div>
                 </div>
                 {!isReadOnly && (
                   <button onClick={() => setUploadStatus('idle')} className="text-xs font-medium text-red-500 hover:text-red-700">Remove</button>
                 )}
              </div>
            )}

            {/* Config Fields */}
            <div className="grid grid-cols-2 gap-4 pt-2">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Installer Type</label>
                <input type="text" name="installer_type" value={formData.installer_type} onChange={handleChange} readOnly={isReadOnly || uploadStatus === 'done'} className={`w-full ${isReadOnly || uploadStatus === 'done' ? 'bg-gray-100 opacity-70' : 'bg-gray-50 focus:bg-white focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 focus:ring-2 focus:ring-[#004aad]/20 outline-none transition-all`} placeholder="e.g. deb" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Install Command</label>
                <input type="text" name="install_command" value={formData.install_command} onChange={handleChange} readOnly={isReadOnly} className={`w-full ${isReadOnly ? 'bg-gray-100' : 'bg-gray-50 focus:bg-white focus:ring-2 focus:ring-[#004aad]/20 focus:border-[#004aad]'} border border-gray-200 rounded-lg px-3 py-2 text-gray-900 outline-none transition-all font-mono text-sm`} placeholder="e.g. sudo dpkg -i {package}" />
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

import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { getInstallationStatus } from '../../services/api';
import { CheckCircle2, Circle, Clock, Terminal } from 'lucide-react';

const InstallationStatus = () => {
  const { id } = useParams();
  const [statusData, setStatusData] = useState({
    step: 'Request Received',
    status: 'pending',
    percentage: 0,
    message: 'Waiting for installation to begin...',
  });
  
  const [consoleLogs, setConsoleLogs] = useState(['Waiting for installation to begin...']);

  const steps = [
    'Request Received',
    'User Validation',
    'Device Validation',
    'Battery Validation',
    'Disk Validation',
    'Dependency Validation',
    'Package Validation',
    'Download Package',
    'Verify Checksum',
    'Installation',
    'Post Installation Validation',
    'Email Notification',
    'Completed'
  ];

  useEffect(() => {
    if (!id) return;
    
    const interval = setInterval(async () => {
      try {
        const data = await getInstallationStatus(id);
        setStatusData(data);
        
        setConsoleLogs(prev => {
          if (prev[prev.length - 1] !== data.message) {
            return [...prev, data.message];
          }
          return prev;
        });

        if (data.status === 'completed' || data.status === 'failed') {
          clearInterval(interval);
        }
      } catch (error) {
        console.error("Failed to get status:", error);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, []);

  const getCurrentStepIndex = () => {
    const index = steps.indexOf(statusData.step);
    return index !== -1 ? index : 0;
  };

  const currentIndex = getCurrentStepIndex();

  return (
    <div className="max-w-4xl mx-auto space-y-8 py-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900 mb-2">Installation Progress</h1>
        <p className="text-gray-500">Monitoring real-time deployment status</p>
      </div>

      <div className="bg-white border border-gray-200 shadow-sm p-8 rounded-2xl relative overflow-hidden">
        {/* Progress Bar Header */}
        <div className="flex justify-between items-end mb-6">
          <div>
            <p className="text-sm text-gray-500 font-medium mb-1">CURRENT STEP</p>
            <h2 className="text-xl font-bold text-[#004aad]">{statusData.step}</h2>
          </div>
          <div className="text-right">
            <span className="text-4xl font-bold text-gray-900">{statusData.percentage}%</span>
          </div>
        </div>

        {/* Global Progress Bar */}
        <div className="h-3 w-full bg-gray-100 rounded-full overflow-hidden mb-10">
          <div 
            className="h-full bg-[#004aad] transition-all duration-500 ease-out rounded-full"
            style={{ width: `${statusData.percentage}%` }}
          />
        </div>

        {/* Stepper */}
        <div className="relative">
          <div className="absolute left-[19px] top-2 bottom-2 w-0.5 bg-gray-200" />
          <div className="space-y-6">
            {steps.map((step, index) => {
              const isCompleted = index < currentIndex || statusData.status === 'completed';
              const isCurrent = index === currentIndex && statusData.status !== 'completed';
              
              return (
                <div key={step} className="relative flex items-center group">
                  <div className="relative z-10 flex items-center justify-center w-10 h-10 rounded-full bg-white border-2 transition-colors duration-300"
                    style={{
                      borderColor: isCompleted ? '#10b981' : isCurrent ? '#004aad' : '#e5e7eb'
                    }}
                  >
                    {isCompleted ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    ) : isCurrent ? (
                      <Clock className="w-5 h-5 text-[#004aad] animate-pulse" />
                    ) : (
                      <Circle className="w-3 h-3 text-gray-300 fill-current" />
                    )}
                  </div>
                  <div className="ml-6 flex-1">
                    <h3 className={`font-medium transition-colors ${
                      isCompleted ? 'text-gray-900' : isCurrent ? 'text-[#004aad]' : 'text-gray-400'
                    }`}>
                      {step}
                    </h3>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        
        {statusData.status === 'completed' && (
           <div className="mt-10 p-4 bg-green-50 border border-green-200 rounded-xl flex items-center">
             <CheckCircle2 className="w-6 h-6 text-green-600 mr-3" />
             <span className="text-green-700 font-medium">Installation completed successfully!</span>
           </div>
        )}
      </div>

      {/* Terminal Console - keeping it dark for contrast */}
      <div className="bg-slate-900 rounded-2xl overflow-hidden shadow-sm">
        <div className="bg-slate-800 px-4 py-3 border-b border-slate-700 flex items-center">
          <Terminal className="w-4 h-4 text-slate-400 mr-2" />
          <span className="text-xs font-medium text-slate-400 font-mono">Live Console</span>
        </div>
        <div className="p-6 font-mono text-sm h-64 overflow-y-auto space-y-2">
          {consoleLogs.map((log, i) => {
            let textColor = 'text-slate-300';
            if (log.includes('completed') || log.includes('successfully')) textColor = 'text-emerald-400';
            if (log.includes('Failed')) textColor = 'text-red-400';
            if (log.includes('Attempt') || log.includes('Remediation')) textColor = 'text-amber-400';
            
            return (
              <div key={i} className="flex">
                <span className="text-slate-500 mr-4">{(i + 1).toString().padStart(3, '0')}</span>
                <span className={textColor}>
                  {log}
                </span>
              </div>
            );
          })}
          {statusData.status !== 'completed' && (
            <div className="flex">
              <span className="text-slate-500 mr-4">{(consoleLogs.length + 1).toString().padStart(3, '0')}</span>
              <span className="w-2 h-4 bg-slate-300 animate-pulse inline-block" />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default InstallationStatus;

import React, { useState, useEffect, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, Circle, Clock, Terminal, AlertTriangle, Loader2, Play, Square } from 'lucide-react';
import { startInstallation, cancelInstallation, identifyHost } from '../../services/api';

const simSteps = [
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

const agenticSteps = [
  'Request Received',
  'User Validation',
  'Device Validation',
  'Host Discovery',
  'Application State Check',
  'Latest Version Discovery',
  'Version Decision',
  'Script Generation',
  'Risk Analysis',
  'FleetDM Upload',
  'Script Execution',
  'Execution Monitoring',
  'Script Cleanup',
  'Verification Generation',
  'Verification Upload',
  'Verification Execution',
  'Verification Monitoring',
  'Verification Cleanup',
  'Email Notification',
  'Completed'
];

const backendToFrontendStageMap = {
  'USER_VALIDATION': 'User Validation',
  'DEVICE_VALIDATION': 'Device Validation',
  'HOST_DISCOVERY': 'Host Discovery',
  'APPLICATION_STATE_CHECK': 'Application State Check',
  'LATEST_VERSION_DISCOVERY': 'Latest Version Discovery',
  'VERSION_DECISION': 'Version Decision',
  'SCRIPT_GENERATION': 'Script Generation',
  'RISK_ANALYSIS': 'Risk Analysis',
  'FLEET_UPLOAD': 'FleetDM Upload',
  'SCRIPT_EXECUTION': 'Script Execution',
  'EXECUTION_MONITORING': 'Execution Monitoring',
  'INSTALLATION_SCRIPT_CLEANUP': 'Script Cleanup',
  'VERIFICATION_SCRIPT_GENERATION': 'Verification Generation',
  'VERIFICATION_UPLOAD': 'Verification Upload',
  'VERIFICATION_EXECUTION': 'Verification Execution',
  'VERIFICATION_MONITORING': 'Verification Monitoring',
  'VERIFICATION_SCRIPT_CLEANUP': 'Verification Cleanup',
  'EMAIL_NOTIFICATION': 'Email Notification'
};

const InstallationStatus = () => {
  const { id } = useParams();

  const [mode, setMode] = useState('unknown'); // 'unknown', 'simulation', 'agentic'

  const [statusData, setStatusData] = useState({
    step: 'Request Received',
    status: 'pending',
    percentage: 0,
    message: 'Waiting for installation to begin...',
  });

  const [consoleLogs, setConsoleLogs] = useState(['Waiting for installation to begin...']);

  // Custom frontend state
  const [activeStep, setActiveStep] = useState('Request Received');
  const [stepTimings, setStepTimings] = useState({}); // { [stepName]: { start, end, duration } }
  const [currentTime, setCurrentTime] = useState(Date.now());

  const [deviceReadiness, setDeviceReadiness] = useState(null);

  // Agentic UI specific states
  const [riskInfo, setRiskInfo] = useState(null);
  const [hostDiscovery, setHostDiscovery] = useState(null);
  const [appStateData, setAppStateData] = useState(null);
  const [fleetExecution, setFleetExecution] = useState(null);
  const [verificationResult, setVerificationResult] = useState(null);

  // Temporary Host Target state
  const [targetIp, setTargetIp] = useState('');
  const [identifiedHost, setIdentifiedHost] = useState(null);
  const [identifyError, setIdentifyError] = useState(null);
  const [isIdentifying, setIsIdentifying] = useState(false);

  const sequencerRef = useRef(null);

  // Live timer tick
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(Date.now()), 100);
    return () => clearInterval(timer);
  }, []);

  const handleStart = async () => {
    if (mode === 'simulation' || mode === 'unknown') {
      if (!targetIp.trim()) {
        setIdentifyError('Please enter your target IP address.');
        return;
      }

      setIsIdentifying(true);
      setIdentifyError(null);
      let hId = null;

      try {
        setConsoleLogs(prev => [...prev, `Identifying host for IP: ${targetIp.trim()}...`]);
        const data = await identifyHost(targetIp.trim());
        hId = data.host_id;
        setIdentifiedHost(data);
      } catch (err) {
        setIdentifyError('Failed to identify host with the provided IP.');
        setIsIdentifying(false);
        return;
      }

      try {
        const payload = { host_id: String(hId) };
        await startInstallation(id, payload);
        setStatusData(prev => ({ ...prev, status: 'RUNNING', message: 'Starting...' }));
        setConsoleLogs(prev => [...prev, 'Starting installation...']);
      } catch (err) {
        console.error("Failed to start installation", err);
      } finally {
        setIsIdentifying(false);
      }
    }
  };

  const handleCancel = async () => {
    try {
      await cancelInstallation(id);
      setStatusData(prev => ({ ...prev, status: 'CANCELLED', message: 'Cancelled by user' }));
      setConsoleLogs(prev => [...prev, 'Installation cancelled by user.']);
    } catch (err) {
      console.error("Failed to cancel installation", err);
    }
  };

  useEffect(() => {
    if (!id) return;

    let isSubscribed = true;

    const fetchInitialStatus = async () => {
      try {
        const response = await fetch(`http://192.168.10.83:8000/install/${id}`);
        if (response.ok) {
          const data = await response.json();
          if (!isSubscribed) return;

          setStatusData({
            step: data.step,
            status: data.status,
            percentage: data.percentage,
            message: data.message
          });

          if (data.logs && data.logs.length > 0) {
            setConsoleLogs(data.logs);
          }

          if (data.device_readiness) {
            setDeviceReadiness(data.device_readiness);
          }

        }
      } catch (err) {
        console.error("Failed to fetch initial status", err);
      }
    };

    fetchInitialStatus();

    const ws = new WebSocket(`ws://192.168.10.83:8000/ws/installation/${id}`);

    ws.onmessage = (event) => {
      if (!isSubscribed) return;
      const data = JSON.parse(event.data);

      if (data.type === 'log') {
        setConsoleLogs(prev => [...prev, data.message]);
        setStatusData(prev => ({ ...prev, message: data.message }));
      } else if (data.type === 'status') {
        // This is the old simulation status event
        setMode(prevMode => {
          let newMode = prevMode;
          if (newMode === 'unknown') {
            if (simSteps.includes(data.step)) {
              newMode = 'simulation';
            }
          }
          return newMode;
        });

        setStatusData(prev => ({
          ...prev,
          status: data.status,
          step: data.step,
          percentage: data.percentage
        }));
      } else {
        // Agentic events
        setMode('agentic');

        if (data.type === 'agent_stage') {
          const frontendStep = backendToFrontendStageMap[data.stage] || data.stage;

          if (data.status === 'STARTED' || data.status === 'RUNNING') {
            setActiveStep(frontendStep);
            setStatusData(prev => ({ ...prev, status: 'RUNNING', step: frontendStep }));

            setStepTimings(prev => {
              const updated = { ...prev };
              if (!updated[frontendStep]) {
                updated[frontendStep] = { start: Date.now(), end: null, duration: 0 };
              }
              return updated;
            });
          } else if (data.status === 'COMPLETED' || data.status === 'FAILED' || data.status === 'BLOCKED') {
            setStepTimings(prev => {
              const updated = { ...prev };
              if (updated[frontendStep]) {
                if (!updated[frontendStep].end) {
                  updated[frontendStep].end = Date.now();
                  updated[frontendStep].duration = (updated[frontendStep].end - updated[frontendStep].start) / 1000;
                }
                updated[frontendStep].status = data.status;
              }

              // If Execution Monitoring finishes, logically Script Execution has also finished
              if (frontendStep === 'Execution Monitoring' && updated['Script Execution'] && !updated['Script Execution'].end) {
                updated['Script Execution'].end = updated[frontendStep].end || Date.now();
                updated['Script Execution'].duration = (updated['Script Execution'].end - updated['Script Execution'].start) / 1000;
                updated['Script Execution'].status = data.status;
              }

              return updated;
            });

            if (data.status === 'FAILED' || data.status === 'BLOCKED') {
              setStatusData(prev => ({ ...prev, status: data.status, step: frontendStep, failedAtStep: frontendStep }));
            }
          }
        } else if (data.type === 'risk_analysis') {
          setRiskInfo({
            score: data.risk_score,
            level: data.risk_level,
            reasons: data.risk_reasons
          });
        } else if (data.type === 'host_discovery') {
          setHostDiscovery({
            hostname: data.hostname,
            host_ids: data.host_ids
          });
        } else if (data.type === 'application_state_result') {
          setAppStateData({
            application_states: data.application_states,
            installed_versions: data.installed_versions,
            available_versions: data.available_versions
          });
        } else if (data.type === 'fleet_execution') {
          setActiveStep('Script Execution'); // Advance to Script Execution when execution happens
          setStepTimings(prev => {
            const updated = { ...prev };
            if (!updated['Script Execution']) {
              updated['Script Execution'] = { start: Date.now(), end: null, duration: 0 };
            }
            return updated;
          });
          setFleetExecution({
            script_id: data.script_id,
            execution_ids: data.execution_ids,
            host_ids: data.host_ids
          });
        } else if (data.type === 'verification') {
          setActiveStep('Verification Monitoring');
          setVerificationResult({
            success: data.verification_result,
            results: data.verification_results
          });
        } else if (data.type === 'installation_complete') {
          setActiveStep('Completed');
          setStatusData(prev => ({ ...prev, status: data.status, step: 'Completed' }));
          setStepTimings(prev => {
            const updated = { ...prev };
            if (!updated['Completed']) {
              updated['Completed'] = { start: Date.now(), end: Date.now(), duration: 0 };
            }

            const now = Date.now();
            Object.keys(updated).forEach(key => {
              if (!updated[key].end) {
                updated[key].end = now;
                updated[key].duration = (now - updated[key].start) / 1000;
                if (!updated[key].status) updated[key].status = data.status;
              }
            });

            return updated;
          });
        }
      }
    };

    ws.onerror = (error) => console.error("WebSocket error:", error);

    return () => {
      isSubscribed = false;
      ws.close();
    };
  }, [id]);

  // Mode Handlers (Simulation)
  useEffect(() => {
    if (mode === 'simulation') {
      setActiveStep(statusData.step);

      setStepTimings(prev => {
        const now = Date.now();
        const updated = { ...prev };

        Object.keys(updated).forEach(key => {
          if (!updated[key].end && key !== statusData.step) {
            updated[key].end = now;
            updated[key].duration = (now - updated[key].start) / 1000;
          }
        });

        if (!updated[statusData.step]) {
          updated[statusData.step] = { start: now, end: null, duration: 0 };
        }
        return updated;
      });
    }
  }, [mode, statusData.step]);

  // Determine which steps array to use
  const currentSteps = mode === 'agentic' ? agenticSteps : simSteps;

  // Calculate display index
  const getStepIndex = (step) => currentSteps.indexOf(step);
  const activeIndex = getStepIndex(activeStep);

  // UI Display percentage
  let displayPercentage = statusData.percentage;
  if (mode === 'agentic') {
    if (statusData.status === 'FAILED' || statusData.status === 'BLOCKED_HIGH_RISK' || statusData.status === 'CANCELLED') {
      // freeze at current index
      displayPercentage = Math.round((activeIndex / (currentSteps.length - 1)) * 100);
    } else if (statusData.status === 'COMPLETED') {
      displayPercentage = 100;
    } else if (activeIndex >= 0) {
      displayPercentage = Math.round((activeIndex / (currentSteps.length - 1)) * 100);
    }
  } else if (mode === 'simulation') {
    if (statusData.status === 'FAILED') displayPercentage = 100;
  }

  const formatDuration = (start, end) => {
    if (!start) return '--';
    const durationMs = end ? (end - start) : (currentTime - start);
    return (durationMs / 1000).toFixed(1) + 's';
  };

  const isFailed = statusData.status === 'FAILED' || statusData.status === 'BLOCKED' || statusData.status === 'BLOCKED_HIGH_RISK' || statusData.status === 'CANCELLED';
  const isBlockedHighRisk = statusData.status === 'BLOCKED_HIGH_RISK' || statusData.status === 'BLOCKED';

  return (
    <div className="max-w-4xl mx-auto space-y-8 py-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 mb-2">Installation Progress</h1>
          <p className="text-gray-500">Monitoring real-time deployment status {mode !== 'unknown' && `(${mode === 'agentic' ? 'Agentic Mode' : 'Simulation Mode'})`}</p>
        </div>
        <div className="flex space-x-3">
          {statusData.status === 'PENDING' && (
            <button
              onClick={handleStart}
              disabled={isIdentifying}
              className={`flex items-center px-4 py-2 ${isIdentifying ? 'bg-gray-400 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-700'} text-white font-medium rounded-lg shadow-sm transition-colors`}
            >
              <Play className="w-4 h-4 mr-2" fill="currentColor" />
              {isIdentifying ? 'Identifying...' : 'Start Installation'}
            </button>
          )}
          {statusData.status === 'RUNNING' && (
            <button
              onClick={handleCancel}
              className="flex items-center px-4 py-2 bg-red-600 hover:bg-red-700 text-white font-medium rounded-lg shadow-sm transition-colors"
            >
              <Square className="w-4 h-4 mr-2" fill="currentColor" />
              Cancel Installation
            </button>
          )}
        </div>
      </div>

      {(mode === 'simulation' || mode === 'unknown') && (statusData.status === 'pending' || statusData.status === 'PENDING') && (
        <div className="mb-8 p-6 bg-white border border-gray-200 shadow-sm rounded-xl">
          <h3 className="text-sm font-bold text-gray-900 mb-4">Enter your IP (Required)</h3>
          <div className="flex space-x-4 items-start">
            <div className="flex-1">
              <label className="block text-sm font-medium text-gray-700 mb-1">Target IP Address</label>
              <input
                type="text"
                value={targetIp}
                onChange={(e) => {
                  setTargetIp(e.target.value);
                  setIdentifyError(null);
                }}
                className="w-full px-4 py-2 border border-emerald-500 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 outline-none transition-all shadow-sm"
                placeholder="e.g. 192.168.8.175"
              />
              <p className="text-xs text-gray-500 mt-1">This is a crucial step to identify the device readiness, battery percentage, network, etc.</p>
            </div>
          </div>

          {identifyError && (
            <div className="mt-4 p-3 bg-red-50 text-red-700 border border-red-200 rounded-lg text-sm flex items-center">
              <AlertTriangle className="w-4 h-4 mr-2" />
              {identifyError}
            </div>
          )}

          {identifiedHost && (
            <div className="mt-4 p-4 bg-blue-50 border border-blue-100 rounded-lg">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="block text-gray-500 font-medium mb-1">Hostname:</span>
                  <span className="font-bold text-gray-900">{identifiedHost.hostname}</span>
                </div>
                <div>
                  <span className="block text-gray-500 font-medium mb-1">Host ID:</span>
                  <span className="font-bold text-gray-900">{identifiedHost.host_id}</span>
                </div>
                <div>
                  <span className="block text-gray-500 font-medium mb-1">IP Address:</span>
                  <span className="font-bold text-gray-900">{identifiedHost.ip_address}</span>
                </div>
                <div>
                  <span className="block text-gray-500 font-medium mb-1">OS:</span>
                  <span className="font-bold text-gray-900">{identifiedHost.operating_system}</span>
                </div>
                <div>
                  <span className="block text-gray-500 font-medium mb-1">Version:</span>
                  <span className="font-bold text-gray-900">{identifiedHost.os_version}</span>
                </div>
                <div>
                  <span className="block text-gray-500 font-medium mb-1">Architecture:</span>
                  <span className="font-bold text-gray-900">{identifiedHost.architecture}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <div className="bg-white border border-gray-200 shadow-sm p-8 rounded-2xl relative overflow-hidden">

        {/* Device Readiness Card */}
        {deviceReadiness && (
          <div className="mb-8 p-4 bg-gray-50 border border-gray-200 rounded-xl">
            <h3 className="text-sm font-bold text-gray-900 mb-3 border-b border-gray-200 pb-2">Device Readiness</h3>
            <div className="grid grid-cols-2 gap-4 text-sm mb-3">
              <div><span className="text-gray-500 font-medium">Battery:</span> <span className="font-bold text-gray-900">{deviceReadiness.battery}%</span></div>
              <div><span className="text-gray-500 font-medium">Network:</span> <span className="font-bold text-gray-900">{deviceReadiness.network}</span></div>
              <div><span className="text-gray-500 font-medium">Minimum Required Battery:</span> <span className="font-bold text-gray-900">{deviceReadiness.minimum_battery}%</span></div>
            </div>
            <p className="text-xs text-gray-500 italic">Make sure your system is sufficiently charged and has a stable network connection during installation.</p>
          </div>
        )}

        {/* Target Devices */}
        {hostDiscovery && (
          <div className="mb-8 p-4 bg-blue-50 border border-blue-200 rounded-xl">
            <h3 className="text-sm font-bold text-blue-900 mb-3 border-b border-blue-200 pb-2">Target Devices</h3>
            <div className="space-y-2 text-sm text-blue-900">
              {hostDiscovery.host_ids && hostDiscovery.host_ids.map(hid => (
                <div key={hid}>
                  <span className="font-bold">Host ID:</span> {hid}
                </div>
              ))}
              {hostDiscovery.hostname && <div><span className="font-bold">Hostname:</span> {hostDiscovery.hostname}</div>}
            </div>
          </div>
        )}

        {/* Application State Check */}
        {appStateData && (
          <div className="mb-8 p-4 bg-indigo-50 border border-indigo-200 rounded-xl">
            <h3 className="text-sm font-bold text-indigo-900 mb-3 border-b border-indigo-200 pb-2">Application State</h3>
            <div className="space-y-4 text-sm">
              {Object.keys(appStateData.application_states || {}).map(hostId => {
                const state = appStateData.application_states[hostId];
                const installed = appStateData.installed_versions?.[hostId];
                const available = appStateData.available_versions?.[hostId];

                let stateColor = "text-indigo-900";
                if (state === "ALREADY_LATEST") stateColor = "text-emerald-700 font-bold";
                else if (state === "INSTALLED_OUTDATED") stateColor = "text-amber-700 font-bold";

                return (
                  <div key={hostId} className="flex flex-col space-y-1 bg-white/50 p-3 rounded-lg border border-indigo-100">
                    <div className="flex justify-between items-center">
                      <span className="font-bold text-indigo-900">Host {hostId}</span>
                      <span className={stateColor}>{state}</span>
                    </div>
                    <div className="text-gray-600">
                      <div><span className="font-medium">Installed Version:</span> {installed || 'None'}</div>
                      <div><span className="font-medium">Latest Available:</span> {available || 'Unknown'}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Risk Analysis UI */}
        {riskInfo && (
          <div className={`mb-8 p-4 border rounded-xl ${riskInfo.level === 'HIGH' ? 'bg-red-50 border-red-200' : riskInfo.level === 'MEDIUM' ? 'bg-amber-50 border-amber-200' : 'bg-gray-50 border-gray-200'}`}>
            <h3 className={`text-sm font-bold mb-3 border-b pb-2 ${riskInfo.level === 'HIGH' ? 'text-red-900 border-red-200' : riskInfo.level === 'MEDIUM' ? 'text-amber-900 border-amber-200' : 'text-gray-900 border-gray-200'}`}>Risk Analysis</h3>
            <div className="flex justify-between items-center mb-3">
              <div><span className="text-gray-500 font-medium">Score:</span> <span className="font-bold text-gray-900">{riskInfo.score}</span></div>
              <div>
                <span className="text-gray-500 font-medium">Risk Level:</span>
                <span className={`font-bold ml-2 ${riskInfo.level === 'HIGH' ? 'text-red-700' : riskInfo.level === 'MEDIUM' ? 'text-amber-700' : 'text-green-700'}`}>{riskInfo.level}</span>
              </div>
            </div>
            {riskInfo.reasons && riskInfo.reasons.length > 0 && (
              <div>
                <span className="text-gray-500 font-medium text-sm">Reasons:</span>
                <ul className="list-disc pl-5 mt-1 text-sm text-gray-700">
                  {riskInfo.reasons.map((reason, i) => <li key={i}>{reason}</li>)}
                </ul>
              </div>
            )}
            {riskInfo.level === 'HIGH' && (
              <div className="mt-3 p-2 bg-red-100 text-red-800 font-bold rounded text-center">
                HIGH RISK - Installation blocked for safety.
              </div>
            )}
          </div>
        )}

        {/* FleetDM Execution UI */}
        {fleetExecution && (
          <div className="mb-8 p-4 bg-gray-50 border border-gray-200 rounded-xl">
            <h3 className="text-sm font-bold text-gray-900 mb-3 border-b border-gray-200 pb-2">FleetDM Execution</h3>
            <div className="text-sm text-gray-800 mb-2">
              <span className="font-medium text-gray-500">Script ID:</span> {fleetExecution.script_id}
            </div>
            {fleetExecution.execution_ids && fleetExecution.execution_ids.length > 0 && (
              <div className="text-sm text-gray-800">
                <span className="font-medium text-gray-500">Execution IDs:</span>
                <ul className="list-disc pl-5 mt-1">
                  {fleetExecution.execution_ids.map((eid, i) => <li key={i}>{eid}</li>)}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Verification Results */}
        {verificationResult && verificationResult.results && (
          <div className="mb-8 p-4 bg-gray-50 border border-gray-200 rounded-xl">
            <h3 className="text-sm font-bold text-gray-900 mb-3 border-b border-gray-200 pb-2">Installation Verification</h3>
            <div className="space-y-2 text-sm">
              {Object.entries(verificationResult.results).map(([hostId, passed]) => (
                <div key={hostId} className="flex items-center">
                  {passed ? <CheckCircle2 className="w-4 h-4 text-emerald-500 mr-2" /> : <AlertTriangle className="w-4 h-4 text-red-500 mr-2" />}
                  <span className={passed ? "text-emerald-700" : "text-red-700"}>Host {hostId}: {passed ? 'Verified' : 'Failed'}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Progress Bar Header */}
        <div className="flex justify-between items-end mb-6">
          <div>
            <p className="text-sm text-gray-500 font-medium mb-1">CURRENT STEP</p>
            <h2 className={`text-xl font-bold ${isFailed ? 'text-red-600' : 'text-[#004aad]'}`}>
              {activeStep}
            </h2>
          </div>
          <div className="text-right">
            <span className={`text-4xl font-bold ${isFailed ? 'text-red-600' : 'text-gray-900'}`}>{displayPercentage}%</span>
          </div>
        </div>

        {/* Global Progress Bar */}
        <div className="h-3 w-full bg-gray-100 rounded-full overflow-hidden mb-10">
          <div
            className={`h-full transition-all duration-500 ease-out rounded-full ${isFailed ? 'bg-red-500' : 'bg-[#004aad]'}`}
            style={{ width: `${displayPercentage}%` }}
          />
        </div>

        {/* Stepper */}
        <div className="relative">
          <div className="absolute left-[19px] top-2 bottom-2 w-0.5 bg-gray-200" />
          <div className="space-y-6">
            {currentSteps.map((step, index) => {
              const stepTiming = stepTimings[step];

              const isFailedStep = (statusData.failedAtStep === step) || (stepTiming && (stepTiming.status === 'FAILED' || stepTiming.status === 'BLOCKED'));

              // A step is completed if it has an end time and didn't fail
              let isCompleted = stepTiming && stepTiming.end && !isFailedStep;
              if (statusData.status === 'COMPLETED' && index <= activeIndex) {
                isCompleted = true; // Fallback for simulation mode / legacy
              }
              if (isFailed && !isFailedStep && index > currentSteps.indexOf(statusData.failedAtStep || activeStep)) {
                isCompleted = false; // Steps after the failure are not completed
              }

              const isCurrent = (index === activeIndex && !isFailed && statusData.status !== 'COMPLETED') ||
                (stepTiming && !stepTiming.end && !isFailed && statusData.status !== 'COMPLETED');

              const durationStr = stepTiming ? formatDuration(stepTiming.start, stepTiming.end) : '--';

              return (
                <div key={step} className="relative flex items-center group">
                  <div className="relative z-10 flex items-center justify-center w-10 h-10 rounded-full bg-white border-2 transition-colors duration-300"
                    style={{
                      borderColor: isFailedStep ? '#ef4444' : isCompleted ? '#10b981' : isCurrent ? '#004aad' : '#e5e7eb'
                    }}
                  >
                    {isFailedStep ? (
                      <AlertTriangle className="w-5 h-5 text-red-500" />
                    ) : isCompleted ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-500" />
                    ) : isCurrent ? (
                      <Loader2 className="w-5 h-5 text-[#004aad] animate-spin" />
                    ) : (
                      <Circle className="w-3 h-3 text-gray-300 fill-current" />
                    )}
                  </div>
                  <div className="ml-6 flex-1 flex justify-between items-center">
                    <div className="flex flex-col">
                      <h3 className={`font-medium transition-colors ${isFailedStep ? 'text-red-600 font-bold' : isCompleted ? 'text-gray-900' : isCurrent ? 'text-[#004aad] font-bold' : 'text-gray-400'
                        }`}>
                        {step}
                      </h3>
                      {isFailedStep && (
                        <span className="text-red-500 text-xs mt-1">Failed</span>
                      )}
                    </div>

                    <div className="text-right flex items-center space-x-2">
                      {isCurrent && <Clock className="w-4 h-4 text-gray-400" />}
                      <span className={`text-sm font-mono ${isCurrent ? 'text-[#004aad]' : 'text-gray-500'}`}>
                        {durationStr}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {statusData.status === 'COMPLETED' && (
          <div className="mt-10 p-4 bg-green-50 border border-green-200 rounded-xl flex items-center">
            <CheckCircle2 className="w-6 h-6 text-green-600 mr-3" />
            <span className="text-green-700 font-medium">
              {appStateData && Object.values(appStateData.application_states || {}).every(s => s === 'ALREADY_LATEST')
                ? "Latest version already installed. Installation not required."
                : "Installation completed successfully!"}
            </span>
          </div>
        )}

        {isBlockedHighRisk && (
          <div className="mt-10 p-5 bg-red-50 border border-red-200 rounded-xl">
            <div className="flex items-center mb-3">
              <AlertTriangle className="w-6 h-6 text-red-600 mr-3" />
              <span className="text-red-700 font-bold text-lg">Installation Blocked</span>
            </div>
            <p className="text-red-600 text-sm mb-4">The deployment was intentionally blocked for safety due to HIGH RISK analysis.</p>
          </div>
        )}

        {isFailed && !isBlockedHighRisk && (
          <div className="mt-10 p-5 bg-red-50 border border-red-200 rounded-xl">
            <div className="flex items-center mb-3">
              <AlertTriangle className="w-6 h-6 text-red-600 mr-3" />
              <span className="text-red-700 font-bold text-lg">Installation Failed</span>
            </div>
            <p className="text-red-600 text-sm mb-4">The deployment was aborted due to an error during the <strong>{statusData.failedAtStep || activeStep}</strong> phase.</p>
            <div className="bg-white/60 p-4 rounded-lg border border-red-100 font-mono text-sm text-red-800">
              {consoleLogs.slice(-3).map((log, i) => (
                <div key={i}>{log}</div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Terminal Console */}
      <div className="bg-slate-900 rounded-2xl overflow-hidden shadow-sm">
        <div className="bg-slate-800 px-4 py-3 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center">
            <Terminal className="w-4 h-4 text-slate-400 mr-2" />
            <span className="text-xs font-medium text-slate-400 font-mono">Live Console</span>
          </div>
          <div className="flex items-center space-x-2">
            <div className={`w-2 h-2 rounded-full ${statusData.status === 'RUNNING' ? 'bg-green-400 animate-pulse' : 'bg-gray-500'}`}></div>
            <span className="text-xs text-slate-500 font-mono">Backend Stream</span>
          </div>
        </div>
        <div className="p-6 font-mono text-sm h-64 overflow-y-auto space-y-2">
          {consoleLogs.map((log, i) => {
            let textColor = 'text-slate-300';
            if (log.includes('completed') || log.includes('successfully')) textColor = 'text-emerald-400';
            if (log.toLowerCase().includes('failed') || log.toLowerCase().includes('error')) textColor = 'text-red-400';
            if (log.includes('Attempt') || log.includes('Remediation')) textColor = 'text-amber-400';
            if (log.includes('HIGH RISK')) textColor = 'text-red-500 font-bold';

            return (
              <div key={i} className="flex">
                <span className="text-slate-500 mr-4">{(i + 1).toString().padStart(3, '0')}</span>
                <span className={textColor}>
                  {log}
                </span>
              </div>
            );
          })}
          {statusData.status === 'RUNNING' && (
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

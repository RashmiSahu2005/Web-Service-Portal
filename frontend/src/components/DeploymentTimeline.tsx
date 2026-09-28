import { Check, Loader2, X, Circle, AlertTriangle } from 'lucide-react';
import type { UseInstallationWSReturn } from '../hooks/useInstallationWS';

type TimelineProps = {
  data: UseInstallationWSReturn;
};

// Map backend stages to UI-friendly labels
const STAGE_LABELS: Record<string, string> = {
  'EMAIL_INTENT_PARSED': 'Intent Classified',
  'APPLICATION_MAPPED': 'Applications Identified',
  'APPROVAL': 'Approval Verified',
  'HOST_DISCOVERY': 'Host Discovered',
  'SCRIPT_REGISTRY_LOOKUP': 'Script Registry Checked',
  'INSTALLATION_RESEARCH': 'Installation Research',
  'INSTALLATION_RESEARCH_VALIDATION': 'Research Validation',
  'SCRIPT_GENERATION': 'Script Generated',
  'SCRIPT_VALIDATION': 'Script Validation',
  'FLEET_UPLOAD': 'Script Uploaded to FleetDM',
  'EXECUTION_MONITORING': 'Executing Installation',
  'VERIFICATION': 'Installation Verification',
  'SCRIPT_FAILURE_ANALYSIS': 'Script Failure Analysis',
  'NOTIFICATION': 'Notification',
};

// The ordered list of steps we want to show
const EXPECTED_ORDER = [
  'EMAIL_INTENT_PARSED',
  'APPLICATION_MAPPED',
  'APPROVAL',
  'HOST_DISCOVERY',
  'SCRIPT_REGISTRY_LOOKUP',
  'INSTALLATION_RESEARCH',
  'INSTALLATION_RESEARCH_VALIDATION',
  'SCRIPT_GENERATION',
  'SCRIPT_VALIDATION',
  'FLEET_UPLOAD',
  'EXECUTION_MONITORING',
  'VERIFICATION',
  'SCRIPT_FAILURE_ANALYSIS', // Will be conditionally skipped/dimmed if not hit
  'NOTIFICATION'
];



export function DeploymentTimeline({ data }: TimelineProps) {
  const { stages, overallStatus, error, researchResult } = data;

  const stepsToShow = EXPECTED_ORDER.filter(step => {
    if (step === 'SCRIPT_FAILURE_ANALYSIS' && !stages[step]) return false;
    if (step === 'INSTALLATION_RESEARCH' && !stages[step] && stages['FLEET_UPLOAD']) {
        return false;
    }
    if (step === 'INSTALLATION_RESEARCH_VALIDATION' && !stages[step] && stages['FLEET_UPLOAD']) {
        return false;
    }
    if (step === 'SCRIPT_GENERATION' && !stages[step] && stages['SCRIPT_REGISTRY_LOOKUP']?.status === 'COMPLETED') {
        return true;
    }
    if (step === 'SCRIPT_VALIDATION' && !stages[step] && stages['SCRIPT_REGISTRY_LOOKUP']?.status === 'COMPLETED') {
        return false;
    }
    if (step === 'VERIFICATION' && !stages[step] && overallStatus !== 'COMPLETED' && overallStatus !== 'FAILED') {
        return true; // Show as pending
    }
    return true;
  });

  return (
    <div className="card">
      <h2 className="card-title">Real-time Deployment Status</h2>
      <div className="timeline">
        {stepsToShow.map((stepKey) => {
          const stageData = stages[stepKey];
          const label = STAGE_LABELS[stepKey] || stepKey;
          
          let status = 'PENDING';
          if (stageData) {
            status = stageData.status;
          }

          // Icon logic
          let Icon = Circle;
          let iconClass = '';
          
          if (status === 'COMPLETED') {
            Icon = Check;
            iconClass = 'completed';
          } else if (status === 'RUNNING') {
            Icon = Loader2;
            iconClass = 'running animate-spin';
          } else if (status === 'FAILED') {
            Icon = X;
            iconClass = 'failed';
          } else {
            Icon = Circle;
            iconClass = 'pending';
          }
          
          let details = null;
          // Show research result details for INSTALLATION_RESEARCH step
          if (stepKey === 'INSTALLATION_RESEARCH' && status === 'COMPLETED' && researchResult) {
              details = (
                <div className="timeline-details">
                  <div>Method: <strong>{researchResult.recommended_method}</strong></div>
                  <div>Sources: {researchResult.sources_count}</div>
                  <div>Confidence: {Math.round(researchResult.confidence * 100)}%</div>
                </div>
              );
          }

          return (
            <div key={stepKey} className="timeline-step">
              <div className={`timeline-icon-container ${iconClass}`}>
                <Icon size={16} />
              </div>
              <div className="timeline-content">
                <div className="timeline-title">
                  <span style={{ color: status === 'PENDING' ? 'var(--text-muted)' : 'inherit' }}>
                    {label}
                  </span>
                  {status === 'COMPLETED' && stageData?.timestamp && (
                    <span className="timeline-time">
                      {/* For actual timing we'd need start/end of stage. We'll just show the time it completed */}
                      {new Date(stageData.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second:'2-digit' })}
                    </span>
                  )}
                </div>
                {details}
              </div>
            </div>
          );
        })}

        {/* Global failure message if any */}
        {overallStatus === 'FAILED' && error && (
          <div className="timeline-step" style={{ marginTop: '1rem' }}>
             <div className={`timeline-icon-container failed`}>
                <AlertTriangle size={16} />
              </div>
              <div className="timeline-content">
                <div className="timeline-title">
                    <span style={{ color: 'var(--error)' }}>Deployment Failed</span>
                </div>
                <div className="timeline-details" style={{ borderColor: 'var(--error-bg)', color: 'var(--error)' }}>
                  {error}
                </div>
              </div>
          </div>
        )}
      </div>
    </div>
  );
}

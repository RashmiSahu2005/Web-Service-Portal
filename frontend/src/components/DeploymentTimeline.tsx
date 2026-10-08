import { Check, Loader2, X, Circle, AlertTriangle, Shield } from 'lucide-react';
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
  'OS_DETECTION': 'OS Detected',
  'APPLICATION_STATE_CHECK': 'Application State Checked',
  'LATEST_VERSION_DISCOVERY': 'Version Discovery',
  'VERSION_DECISION': 'Version Decision',
  'SCRIPT_REGISTRY_LOOKUP': 'Script Registry Checked',
  'INSTALLATION_RESEARCH': 'Installation Research',
  'INSTALLATION_RESEARCH_VALIDATION': 'Research Validation',
  'SCRIPT_GENERATION': 'Script Generation',
  'SCRIPT_VALIDATION': 'Script Validation',
  'RISK_ANALYSIS': 'Risk Analysis',
  'FLEET_UPLOAD': 'Uploaded to FleetDM',
  'EXECUTION_MONITORING': 'Execution',
  'VERIFICATION': 'Verification',
  'SCRIPT_FAILURE_ANALYSIS': 'Script Failure Analysis',
  'NOTIFICATION': 'Notification',
  'EMAIL_NOTIFICATION': 'Notification',
};

// The ordered list of steps we want to show matching the requested sequence:
// Intent Classified → Applications Identified → Approval Verified → Host Discovered →
// Application State Checked → Version Discovery → Version Decision → Script Generation →
// Execution → Verification → Notification
const EXPECTED_ORDER = [
  'EMAIL_INTENT_PARSED',
  'APPLICATION_MAPPED',
  'APPROVAL',
  'HOST_DISCOVERY',
  'APPLICATION_STATE_CHECK',
  'LATEST_VERSION_DISCOVERY',
  'VERSION_DECISION',
  'SCRIPT_GENERATION',
  'EXECUTION_MONITORING',
  'VERIFICATION',
  'NOTIFICATION'
];

// Map application-level failure categories to human-readable messages
export const FAILURE_CATEGORY_LABELS: Record<string, string> = {
  'VERSION_DETECTION_FAILED': 'Unable to determine installed version on host',
  'APPLICATION_NOT_INSTALLED': 'Application is genuinely absent on this host',
  'VERSION_DISCOVERY_FAILED': 'Trustworthy latest version could not be established',
  'VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST': 'Downgrade requires explicit user clarification',
  'STATE_CHECK_FAILED': 'Application state check failed',
  'CURRENT_VERSION_UNKNOWN': 'Current installed version is unknown',
  'VERSION_COMPARISON_FAILED': 'Version comparison error',
  'NO_UPDATE_REQUIRED': 'Application is already at or newer than latest version',
};

export function DeploymentTimeline({ data }: TimelineProps) {
  const { stages, overallStatus, error, appState } = data;

  const stepsToShow = EXPECTED_ORDER.filter(step => {
    if (step === 'SCRIPT_FAILURE_ANALYSIS' && !stages[step]) return false;
    return true;
  });

  // Detect version detection and decision states from appState
  const appStates = appState?.application_states || {};
  const hasVersionDetectionFailed = Object.values(appStates).some(
    (s) => s === 'VERSION_DETECTION_FAILED' || s === 'STATE_CHECK_FAILED'
  );
  const hasAppNotInstalled = Object.values(appStates).some(
    (s) => s === 'APPLICATION_NOT_INSTALLED'
  );
  const hasVersionDiscoveryFailed = Object.values(appStates).some(
    (s) => s === 'VERSION_DISCOVERY_FAILED'
  );
  const hasDowngradeClarification = Object.values(appStates).some(
    (s) => s === 'VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST'
  );
  const hasNoUpdateRequired = Object.values(appStates).some(
    (s) => s === 'NO_UPDATE_REQUIRED'
  );

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

          // If state-check completed but version detection failed, mark it as failed
          if (stepKey === 'APPLICATION_STATE_CHECK' && status === 'COMPLETED' &&
              (hasVersionDetectionFailed || hasAppNotInstalled)) {
            status = 'FAILED';
          }

          // If version discovery failed
          if (stepKey === 'LATEST_VERSION_DISCOVERY' && (hasVersionDiscoveryFailed || (status === 'COMPLETED' && hasVersionDiscoveryFailed))) {
            status = 'FAILED';
          }

          // If downgrade clarification is needed
          if (stepKey === 'VERSION_DECISION' && hasDowngradeClarification) {
            status = 'BLOCKED';
          }

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
          } else if (status === 'BLOCKED') {
            Icon = Shield;
            iconClass = 'failed';
          } else {
            Icon = Circle;
            iconClass = 'pending';
          }

          let details = null;

          // Show failure detail for APPLICATION_STATE_CHECK
          if (stepKey === 'APPLICATION_STATE_CHECK' && status === 'FAILED') {
            const failMsg = hasVersionDetectionFailed
              ? 'Unable to determine installed version — UPDATE BLOCKED'
              : hasAppNotInstalled
              ? 'Application is not installed on this host — Submit an installation request'
              : 'State check failed';
            details = (
              <div className="timeline-details" style={{ borderColor: 'var(--error-bg)', color: 'var(--error)' }}>
                {failMsg}
              </div>
            );
          }

          // Show failure detail for LATEST_VERSION_DISCOVERY
          if (stepKey === 'LATEST_VERSION_DISCOVERY' && (status === 'FAILED' || hasVersionDiscoveryFailed)) {
            details = (
              <div className="timeline-details" style={{ borderColor: 'var(--error-bg)', color: 'var(--error)' }}>
                VERSION_DISCOVERY_FAILED: Could not establish a trustworthy newer version from authoritative vendor feeds
              </div>
            );
          }

          // Show detail for VERSION_DECISION
          if (stepKey === 'VERSION_DECISION') {
            if (hasDowngradeClarification) {
              details = (
                <div className="timeline-details" style={{ borderColor: 'var(--warning, #eab308)', color: 'var(--warning, #eab308)' }}>
                  Awaiting User Clarification: Target version is lower than installed version (Downgrade protection)
                </div>
              );
            } else if (hasNoUpdateRequired) {
              details = (
                <div className="timeline-details" style={{ borderColor: 'var(--success)', color: 'var(--success)' }}>
                  NO_UPDATE_REQUIRED: Application is already at or newer than the authoritative latest version
                </div>
              );
            }
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

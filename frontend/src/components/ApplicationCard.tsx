import { CheckCircle2, XCircle, Clock } from 'lucide-react';
import type { UseInstallationWSReturn } from '../hooks/useInstallationWS';

type ApplicationCardProps = {
  data: UseInstallationWSReturn;
};

export function ApplicationCard({ data }: ApplicationCardProps) {
  const { appState, overallStatus, fleetExecution, requestSummary } = data;

  const appNames = new Set<string>();
  if (appState && appState.application_states) {
    Object.keys(appState.application_states).forEach(n => appNames.add(n));
  }
  if (requestSummary && requestSummary.applications) {
    requestSummary.applications.forEach(n => appNames.add(n));
  }

  const appList = Array.from(appNames);

  if (appList.length === 0) {
    return (
      <div className="card">
        <h2 className="card-title">Applications</h2>
        <div className="empty-state">
          <Clock className="animate-spin" size={24} style={{ margin: '0 auto 1rem', color: 'var(--text-light)' }} />
          <p>Identifying requested applications...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="card-title">Application Status</h2>
      
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {appList.map((appName) => {
          const state = appState?.application_states[appName] || 'PROCESSING';
          const installedVersion = appState?.installed_versions[appName];
          const availableVersion = appState?.available_versions[appName];
          
          let Icon = Clock;
          let iconColor = 'var(--primary)';
          let badgeText = 'Processing...';
          let badgeClass = 'badge-primary';

          if (state === 'INSTALLED' || state === 'UP_TO_DATE' || state === 'NO_UPDATE_REQUIRED' || state === 'ALREADY_TARGET_VERSION') {
              Icon = CheckCircle2;
              iconColor = 'var(--success)';
              badgeText = 'Ready / Up to Date';
              badgeClass = 'badge-success';
          } else if (overallStatus === 'COMPLETED') {
              Icon = CheckCircle2;
              iconColor = 'var(--success)';
              badgeText = 'Success';
              badgeClass = 'badge-success';
          } else if (overallStatus === 'FAILED' || state === 'FAILED' || state === 'UPDATE_BLOCKED') {
              Icon = XCircle;
              iconColor = 'var(--error)';
              badgeText = state === 'UPDATE_BLOCKED' ? 'Update Blocked' : 'Failed';
              badgeClass = 'badge-error';
          } else if (state === 'VERSION_DOWNGRADE_REQUIRES_EXPLICIT_REQUEST') {
              Icon = XCircle;
              iconColor = 'var(--error)';
              badgeText = 'Downgrade Blocked';
              badgeClass = 'badge-error';
          } else {
              Icon = Clock;
              iconColor = 'var(--primary)';
              badgeText = 'Running...';
              badgeClass = 'badge-primary';
          }

          return (
            <div key={appName} style={{ border: '1px solid var(--border-color)', borderRadius: '6px', padding: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Icon size={20} color={iconColor} />
                  <span style={{ fontWeight: 600 }}>{appName}</span>
                </div>
                <span className={`badge ${badgeClass}`}>
                  {badgeText}
                </span>
              </div>
              
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                 <div>
                    <span style={{ display: 'block', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-light)' }}>Target Version</span>
                    {availableVersion || 'Latest'}
                 </div>
                 <div>
                    <span style={{ display: 'block', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-light)' }}>Installed Version</span>
                    {installedVersion || 'None'}
                 </div>
              </div>
              
              {fleetExecution && fleetExecution.script_id && (
                  <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--border-color)', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      Script ID: {fleetExecution.script_id}
                  </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

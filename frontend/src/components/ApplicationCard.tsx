import { CheckCircle2, XCircle, Clock } from 'lucide-react';
import type { UseInstallationWSReturn } from '../hooks/useInstallationWS';

type ApplicationCardProps = {
  data: UseInstallationWSReturn;
};

export function ApplicationCard({ data }: ApplicationCardProps) {
  const { appState, overallStatus, fleetExecution } = data;

  // We infer the applications from appState. If null, we just show a generic loading state.
  if (!appState || Object.keys(appState.application_states).length === 0) {
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
        {Object.entries(appState.application_states).map(([appName, state]) => {
          // If we have an installed version, show it.
          const installedVersion = appState.installed_versions[appName];
          const availableVersion = appState.available_versions[appName];
          
          let Icon = Clock;
          let iconColor = 'var(--text-light)';
          
          if (overallStatus === 'COMPLETED' || state === 'INSTALLED' || state === 'UP_TO_DATE') {
              Icon = CheckCircle2;
              iconColor = 'var(--success)';
          } else if (overallStatus === 'FAILED') {
              Icon = XCircle;
              iconColor = 'var(--error)';
          } else {
              Icon = Clock;
              iconColor = 'var(--primary)';
          }

          return (
            <div key={appName} style={{ border: '1px solid var(--border-color)', borderRadius: '6px', padding: '1rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Icon size={20} color={iconColor} />
                  <span style={{ fontWeight: 600 }}>{appName}</span>
                </div>
                <span className={`badge ${overallStatus === 'COMPLETED' ? 'badge-success' : overallStatus === 'FAILED' ? 'badge-error' : 'badge-primary'}`}>
                  {overallStatus === 'COMPLETED' ? 'Success' : overallStatus === 'FAILED' ? 'Failed' : 'Installing...'}
                </span>
              </div>
              
              <div style={{ fontSize: '0.875rem', color: 'var(--text-muted)', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                 <div>
                    <span style={{ display: 'block', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-light)' }}>Target Version</span>
                    {availableVersion || 'Latest'}
                 </div>
                 {installedVersion && (
                     <div>
                        <span style={{ display: 'block', textTransform: 'uppercase', fontSize: '0.7rem', fontWeight: 600, color: 'var(--text-light)' }}>Installed Version</span>
                        {installedVersion}
                     </div>
                 )}
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

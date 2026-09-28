import { User, Mail, Package } from 'lucide-react';
import type { UseInstallationWSReturn } from '../hooks/useInstallationWS';

type RequestSummaryProps = {
  data: UseInstallationWSReturn;
};

export function RequestSummary({ data }: RequestSummaryProps) {
  const { requestSummary } = data;

  if (!requestSummary) return null;

  return (
    <div className="card">
      <h2 className="card-title">Request Information</h2>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <User size={18} color="var(--text-muted)" style={{ marginTop: '0.1rem' }} />
          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-light)', textTransform: 'uppercase' }}>Requester</div>
            <div style={{ fontWeight: 500 }}>{requestSummary.sender}</div>
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Mail size={18} color="var(--text-muted)" style={{ marginTop: '0.1rem' }} />
          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-light)', textTransform: 'uppercase' }}>Subject</div>
            <div style={{ fontWeight: 500 }}>{requestSummary.subject}</div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Package size={18} color="var(--text-muted)" style={{ marginTop: '0.1rem' }} />
          <div>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-light)', textTransform: 'uppercase' }}>Requested Applications</div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginTop: '0.25rem' }}>
              {requestSummary.applications.map((app) => (
                <span key={app} style={{ padding: '0.1rem 0.5rem', backgroundColor: 'var(--bg-color)', border: '1px solid var(--border-color)', borderRadius: '4px', fontSize: '0.875rem' }}>
                  {app}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState, useEffect } from 'react';
import './App.css';
import { useInstallationWS } from './hooks/useInstallationWS';
import { DeploymentTimeline } from './components/DeploymentTimeline';
import { ExecutionLogs } from './components/ExecutionLogs';
import { ApplicationCard } from './components/ApplicationCard';
import { RequestSummary } from './components/RequestSummary';
import { ArrowLeft } from 'lucide-react';

function App() {
  const [jobId, setJobId] = useState<string>('');
  const [inputJobId, setInputJobId] = useState('');

  // Handle URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('job_id');
    if (id) {
      setJobId(id);
      setInputJobId(id);
    }
  }, []);

  const wsData = useInstallationWS(jobId);

  const handleConnect = (e: React.FormEvent) => {
    e.preventDefault();
    if (inputJobId.trim()) {
      setJobId(inputJobId.trim());
      const url = new URL(window.location.href);
      url.searchParams.set('job_id', inputJobId.trim());
      window.history.pushState({}, '', url);
    }
  };

  const handleBack = () => {
    setJobId('');
    setInputJobId('');
    const url = new URL(window.location.href);
    url.searchParams.delete('job_id');
    window.history.pushState({}, '', url);
  };

  if (!jobId) {
    return (
      <div className="container">
        <div className="header">
          <h1>DeployIQ Real-time Pipeline</h1>
          <p>Enter a Job ID to monitor an active deployment.</p>
        </div>
        <div className="card">
          <form onSubmit={handleConnect} className="input-group" style={{ marginBottom: 0 }}>
            <input
              type="text"
              placeholder="e.g. job_1234abcd"
              value={inputJobId}
              onChange={(e) => setInputJobId(e.target.value)}
              className="input-field"
            />
            <button type="submit" className="btn">Monitor</button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="container">
      <div className="header" style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
        <button 
          onClick={handleBack} 
          className="btn" 
          style={{ padding: '0.5rem', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: 'transparent', color: 'var(--text-muted)', border: '1px solid var(--border-color)', marginTop: '0.25rem' }}
          title="Go back"
        >
          <ArrowLeft size={20} />
        </button>
        <div>
          <h1>DeployIQ Installation</h1>
          <p>Real-time deployment status for {jobId}</p>
          {!wsData.isConnected && (
              <span className="badge badge-warning" style={{ marginTop: '0.5rem', display: 'inline-block' }}>Disconnected</span>
          )}
        </div>
      </div>

      <div className="dashboard-grid">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <DeploymentTimeline data={wsData} />
          <ExecutionLogs logs={wsData.logs} />
        </div>
        
        <div>
          <RequestSummary data={wsData} />
          <ApplicationCard data={wsData} />
          
          {wsData.verificationResult && (
             <div className="card" style={{ marginTop: '1.5rem' }}>
                <h2 className="card-title">Verification Results</h2>
                <div style={{ fontSize: '0.875rem' }}>
                   {Object.entries(wsData.verificationResult.verification_results).map(([app, result]) => (
                      <div key={app} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-color)' }}>
                         <span>{app}</span>
                         <span className={result ? 'log-success' : 'log-error'} style={{ fontWeight: 600 }}>
                            {result ? 'SUCCESS' : 'FAILED'}
                         </span>
                      </div>
                   ))}
                </div>
             </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;

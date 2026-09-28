import { useEffect, useRef } from 'react';
import type { LogEvent } from '../hooks/useInstallationWS';

type ExecutionLogsProps = {
  logs: LogEvent[];
};

export function ExecutionLogs({ logs }: ExecutionLogsProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  if (logs.length === 0) {
    return (
      <div className="card">
        <h2 className="card-title">Execution Details</h2>
        <div className="logs-container">
          <div className="log-entry log-info">Waiting for logs...</div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2 className="card-title">Execution Details</h2>
      <div className="logs-container">
        {logs.map((log) => {
          // parse time from ISO string
          const date = new Date(log.timestamp);
          const timeString = `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`;
          
          return (
            <div key={log.id} className="log-entry">
              <span className="log-time">{timeString}</span>
              <span className={log.isError ? 'log-error' : 'log-info'}>
                {log.message}
              </span>
            </div>
          );
        })}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

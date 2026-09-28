import { useState, useEffect, useRef } from 'react';

export type AgentStage = {
  stage: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  timestamp: string;
};

export type AppStateResult = {
  application_states: Record<string, string>;
  installed_versions: Record<string, string>;
  available_versions: Record<string, string>;
};

export type LogEvent = {
  id: string;
  message: string;
  timestamp: string;
  isError: boolean;
};

export type RiskAnalysis = {
  risk_score: number;
  risk_level: string;
  risk_reasons: string[];
};

export type FleetExecution = {
  script_id: string;
  execution_ids: string[];
  host_ids: number[];
};

export type VerificationResult = {
  verification_result: boolean;
  verification_results: Record<string, boolean>;
};

export type NotificationResult = {
  email_sent: boolean;
  status: string;
};

export type RequestSummaryType = {
  sender: string;
  subject: string;
  applications: string[];
};

export type ResearchResult = {
  application: string;
  recommended_method: string;
  confidence: number;
  sources_count: number;
  sources: string[];
  warnings: string[];
  attempt: number;
};

export type UseInstallationWSReturn = {
  isConnected: boolean;
  requestSummary: RequestSummaryType | null;
  stages: Record<string, AgentStage>;
  logs: LogEvent[];
  appState: AppStateResult | null;
  riskAnalysis: RiskAnalysis | null;
  fleetExecution: FleetExecution | null;
  verificationResult: VerificationResult | null;
  notificationResult: NotificationResult | null;
  researchResult: ResearchResult | null;
  overallStatus: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED';
  error: string | null;
};

export function useInstallationWS(jobId: string): UseInstallationWSReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [requestSummary, setRequestSummary] = useState<RequestSummaryType | null>(null);
  const [stages, setStages] = useState<Record<string, AgentStage>>({});
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [appState, setAppState] = useState<AppStateResult | null>(null);
  const [riskAnalysis, setRiskAnalysis] = useState<RiskAnalysis | null>(null);
  const [fleetExecution, setFleetExecution] = useState<FleetExecution | null>(null);
  const [verificationResult, setVerificationResult] = useState<VerificationResult | null>(null);
  const [notificationResult, setNotificationResult] = useState<NotificationResult | null>(null);
  const [researchResult, setResearchResult] = useState<ResearchResult | null>(null);
  const [overallStatus, setOverallStatus] = useState<'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED'>('PENDING');
  const [error, setError] = useState<string | null>(null);

  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!jobId) return;

    // Connect to backend WebSocket
    const wsUrl = `ws://${window.location.hostname}:8000/ws/installation/${jobId}`;
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    ws.current.onclose = () => {
      setIsConnected(false);
    };

    ws.current.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('Connection to backend failed');
    };

    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const timestamp = new Date().toISOString();

        switch (data.type) {
          case 'agent_stage':
            setStages((prev) => ({
              ...prev,
              [data.stage]: {
                stage: data.stage,
                status: data.status,
                timestamp: data.timestamp || timestamp,
              },
            }));
            if (data.status === 'RUNNING' && overallStatus === 'PENDING') {
              setOverallStatus('RUNNING');
            }
            break;

          case 'request_summary':
            setRequestSummary({
              sender: data.sender,
              subject: data.subject,
              applications: data.applications || [],
            });
            break;

          case 'log':
            setLogs((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                message: data.message,
                timestamp: timestamp,
                isError: data.message.toLowerCase().includes('failed') || data.message.toLowerCase().includes('error'),
              },
            ]);
            break;

          case 'application_state_result':
            setAppState({
              application_states: data.application_states || {},
              installed_versions: data.installed_versions || {},
              available_versions: data.available_versions || {},
            });
            break;

          case 'risk_analysis':
            setRiskAnalysis({
              risk_score: data.risk_score,
              risk_level: data.risk_level,
              risk_reasons: data.risk_reasons || [],
            });
            break;

          case 'fleet_execution':
            setFleetExecution({
              script_id: data.script_id,
              execution_ids: data.execution_ids || [],
              host_ids: data.host_ids || [],
            });
            break;

          case 'verification':
            setVerificationResult({
              verification_result: data.verification_result,
              verification_results: data.verification_results || {},
            });
            break;

          case 'notification':
            setNotificationResult({
              email_sent: data.email_sent,
              status: data.status,
            });
            break;

          case 'research_result':
            setResearchResult({
              application: data.application,
              recommended_method: data.recommended_method,
              confidence: data.confidence,
              sources_count: data.sources_count,
              sources: data.sources || [],
              warnings: data.warnings || [],
              attempt: data.attempt,
            });
            break;

          case 'installation_complete':
            setOverallStatus(data.status === 'SUCCESS' ? 'COMPLETED' : 'FAILED');
            if (data.error) {
              setError(data.error);
            }
            break;

          case 'status':
            // Legacy/fallback status structure
            if (data.status === 'FAILED') {
                setOverallStatus('FAILED');
            } else if (data.status === 'COMPLETED') {
                setOverallStatus('COMPLETED');
            } else if (data.status === 'RUNNING' && overallStatus === 'PENDING') {
                setOverallStatus('RUNNING');
            }
            break;
            
          default:
            console.warn('Unknown event type received:', data);
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [jobId]);

  return {
    isConnected,
    requestSummary,
    stages,
    logs,
    appState,
    riskAnalysis,
    fleetExecution,
    verificationResult,
    notificationResult,
    researchResult,
    overallStatus,
    error,
  };
}

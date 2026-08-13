from typing import TypedDict, List, Optional
from datetime import datetime

class InstallationState(TypedDict, total=False):
    # Job/Application Metadata
    job_id: str
    application_id: str
    application_name: str
    version: str
    
    requested_version: Optional[str] # added for version selection
    target_version: Optional[str] # added for version selection
    version_resolution_source: Optional[str] # added for version selection
    version_availability_status: Optional[str] # added for version selection
    discovered_latest_version: Optional[str]
    version_check_unavailable: Optional[bool]

    category: Optional[str]
    description: Optional[str]
    install_command: Optional[str]
    
    # Target Host Information
    hostname: Optional[str]
    ip_address: Optional[str]
    host_ids: List[int]
    
    # Target OS Specs (Multi-Host OS Groups)
    os_details: dict # host_id -> {"os": str, "os_version": str, "architecture": str}
    os_groups: dict # os_signature (e.g. Ubuntu_22.04_amd64) -> List[int] (host_ids)
    
    # Application State
    application_states: dict # e.g. {host_id: "ALREADY_LATEST"}
    installed_versions: dict # e.g. {host_id: "1.0.0"}
    available_versions: dict # e.g. {host_id: "1.0.1"}
    hosts_requiring_installation: List[int]
    
    # Validation/Requirements
    minimum_battery_percentage: Optional[int]
    
    # Application Strategy (Per OS Group)
    strategies: dict # os_signature -> dict
    strategy_reused: dict # os_signature -> bool
    
    # Script Generation & Registry (Per OS Group)
    script_contents: dict # os_signature -> str
    script_hashes: dict # os_signature -> str
    script_reused: dict # os_signature -> bool
    script_registry_ids: dict # os_signature -> int
    
    # Risk Analysis (Per OS Group)
    risk_scores: dict # os_signature -> int
    risk_levels: dict # os_signature -> str
    risk_reasons_map: dict # os_signature -> List[str]
    
    # FleetDM Execution (Per OS Group)
    fleet_script_ids: dict # os_signature -> str
    execution_ids: List[str] # All execution IDs across all OS groups
    execution_results: dict # exec_id -> result
    installation_script_deleted: dict # os_signature -> bool
    installation_cleanup_error: dict # os_signature -> str
    installation_timeout: dict # os_signature -> bool
    
    # Retry and Fallback tracking (Per OS Group)
    current_attempts: dict # os_signature -> int
    maximum_attempts: dict # os_signature -> int
    current_script_type: dict # os_signature -> str
    script_failure_context: dict # os_signature -> List[dict]
    
    # Verification
    verification_script_contents: dict # os_signature -> str
    verification_fleet_script_ids: dict # os_signature -> str
    verification_execution_ids: List[str]
    verification_execution_results: dict
    verification_script_deleted: dict # os_signature -> bool
    verification_cleanup_error: dict # os_signature -> str
    verification_timeout: dict # os_signature -> bool
    verification_result: Optional[bool]
    verification_results: dict # host_id -> bool
    
    # Status Tracking
    current_stage: str
    status: str
    error_message: Optional[str]
    email_sent: Optional[bool]
    is_cancelled: Optional[bool]
    
    # Timestamps
    started_at: datetime
    completed_at: Optional[datetime]

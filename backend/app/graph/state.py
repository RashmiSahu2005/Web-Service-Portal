from typing import TypedDict, List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

class InstallationAttempt(BaseModel):
    attempt_number: int
    strategy: str
    script_id: Optional[str] = None
    script: str = ""
    exit_code: Optional[int] = None
    output: str = ""
    error: Optional[str] = None
    root_cause: Optional[str] = None
    corrective_action: Optional[str] = None
    verification_result: Optional[dict] = None

class InstallationResearch(BaseModel):
    application_name: str
    platform: str
    architecture: str
    
    latest_version: Optional[str] = None
    version_source_url: Optional[str] = None
    
    recommended_method: Optional[str] = None
    installation_method: Optional[str] = None
    package_manager: Optional[str] = None
    package_source: Optional[str] = None
    source_type: Optional[str] = None
    installation_command: Optional[str] = None
    
    artifact_url: Optional[str] = None
    artifact_url_verified: bool = False
    package_type: Optional[str] = None
    
    repository: Optional[str] = None
    repository_url: Optional[str] = None
    
    package_name: Optional[str] = None
    
    verification_method: Optional[str] = None
    verification_command: Optional[str] = None
    
    executable_path: Optional[str] = None
    
    requires_sudo: Optional[bool] = None
    requires_gui: Optional[bool] = None
    
    host_compatibility: Optional[str] = None
    incompatible_constraints: List[str] = Field(default_factory=list)
    expected_duration: Optional[int] = None
    

    notes: List[str] = Field(default_factory=list)
    source_urls: List[str] = Field(default_factory=list)
    
    source_type: Optional[str] = None
    artifact_required: bool = False
    requires_user_artifact: bool = False
    
    confidence: float = 0.0
    research_status: str = "RESEARCH_SUCCESS"
    update_requires_removal: bool = False

class InstallationState(TypedDict, total=False):
    # Job/Application Metadata
    job_id: str
    approval_request_id: Optional[str]
    is_resume_update: Optional[bool]

    
    # Canonical Multi-Application List
    applications: List[dict] 
    # [{"application_name": str, "application_id": str, "requested_version": str, "target_version": str, "version_resolution_source": str, "status": str, "installation_status": str, "verification_status": str}]
    
    # Legacy Fields (mapped to applications[0] for backward compatibility)
    application_id: str
    application_name: str
    version: str
    operation: str
    requester_email: Optional[str]
    
    requested_version: Optional[str] # legacy
    target_version: Optional[str] # legacy
    version_resolution_source: Optional[str] # legacy
    version_availability_status: Optional[str] # legacy
    discovered_latest_version: Optional[str] # legacy
    version_check_unavailable: Optional[bool] # legacy

    category: Optional[str]
    description: Optional[str]
    install_command: Optional[str]
    
    # Target Host Information
    hostname: Optional[str]
    ip_address: Optional[str]
    host_ids: List[int]
    host_constraints: dict # host_id -> dict of constraints
    
    # Target OS Specs (Multi-Host OS Groups)
    os_details: dict # host_id -> {"os": str, "os_version": str, "architecture": str}
    os_groups: dict # os_signature (e.g. Ubuntu_22.04_amd64) -> List[int] (host_ids)
    
    # Application State Checks
    application_states: dict # host_id -> {app_name: state_str}
    installed_versions: dict # host_id -> {app_name: version_str}
    latest_versions_from_host: dict # host_id -> {app_name: version_str}
    available_versions: dict # host_id -> {app_name: version_str}
    hosts_requiring_installation: List[int]
    
    # Validation/Requirements
    minimum_battery_percentage: Optional[int]
    
    # Application Strategy (Per OS Group)
    strategies: dict # os_signature -> {app_name: strategy_dict}
    strategy_reused: dict # os_signature -> bool

    # Installation Research (Per OS Group) — NEW
    # Separate from Script Registry: stores current installation *knowledge*, not proven scripts.
    research_results: dict  # os_signature -> InstallationStrategy dict
    research_skipped: dict  # os_signature -> bool (True when script was reused)
    research_attempts: dict # os_signature -> int
    max_research_attempts: dict # os_signature -> int
    tavily_attempted: dict # os_signature -> bool
    
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
    cached_script_failures: dict # os_signature -> {fleet_script_id, reason, error_message}
    installation_attempts: dict # os_signature -> List[dict] (dumped InstallationAttempt)
    
    # Overall Status Tracking
    current_stage: str
    status: str
    error_message: Optional[str]
    email_sent: Optional[bool]
    is_cancelled: Optional[bool]
    current_app_index: int
    
    # Timestamps
    started_at: datetime
    completed_at: Optional[datetime]
    
    # Stage Timestamps (Per App)
    application_start_time: Optional[float]
    research_start_time: Optional[float]
    research_end_time: Optional[float]
    script_generation_start_time: Optional[float]
    script_generation_end_time: Optional[float]
    fleet_execution_start_time: Optional[float]
    fleet_execution_end_time: Optional[float]
    verification_start_time: Optional[float]
    verification_end_time: Optional[float]
    application_end_time: Optional[float]

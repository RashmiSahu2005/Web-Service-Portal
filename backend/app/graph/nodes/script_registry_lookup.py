from app.graph.state import InstallationState
from app.services.script_registry_service import ScriptRegistryService
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def script_registry_lookup(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "ScriptRegistryAgent"
    stage_name = "SCRIPT_REGISTRY_LOOKUP"

    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")

    # Broadcast request summary to the frontend
    sender_email = state.get("requester_email", "Unknown")
    applications = state.get("applications", [])
    app_names_summary = [app.get("name") for app in applications] if applications else [state.get("application_name", "Unknown")]
    AgentEventService.broadcast_request_summary(job_id, sender_email, "Application Installation Request", app_names_summary)

    broadcast_log(job_id, agent_name, "Looking up compatible script in registry")

    updates = {}

    # If the state status is already FAILED, skip
    if state.get("status") in ["FAILED", "TIMEOUT", "BLOCKED_HIGH_RISK"]:
        broadcast_log(job_id, agent_name, f"Skipping lookup because installation status is {state.get('status')}")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return updates

    # ── KEY FIX: look up the CURRENT application only, not a combined key ────
    # The graph processes applications one at a time (via prepare_current_application).
    # application_name = current app being processed
    # target_version   = resolved by version_decision (exact version, e.g. "1.95.101")
    app_name = state.get("application_name")
    # target_version is the authoritative resolved version from version_decision
    target_version = state.get("target_version") or state.get("version", "latest")

    os_groups = state.get("os_groups", {})

    updates["script_registry_ids"] = {}
    updates["script_hashes"] = {}
    updates["risk_scores"] = {}
    updates["risk_levels"] = {}
    updates["risk_reasons_map"] = {}

    updates["script_reused"] = {}
    updates["script_contents"] = {}
    updates["fleet_script_ids"] = {}
    updates["current_script_type"] = {}

    for sig in os_groups.keys():
        parts = sig.split("_")
        os_name = parts[0]
        arch = parts[-1]

        norm_name = ScriptRegistryService.normalize_application_name(app_name)
        canonical_name = ScriptRegistryService.get_canonical_name(app_name)

        broadcast_log(job_id, agent_name,
            f"[ScriptResolver] Application: {app_name}")
        broadcast_log(job_id, agent_name,
            f"[ScriptResolver] Normalized: {norm_name} → canonical: {canonical_name}")
        broadcast_log(job_id, agent_name,
            f"[ScriptResolver] OS: {os_name}  arch: {arch}  Version: {target_version}")
        broadcast_log(job_id, agent_name,
            f"[ScriptResolver] Checking PostgreSQL registry...")

        script = ScriptRegistryService.resolve_script(
            application_name=app_name,
            version=target_version,
            operating_system=os_name,
            architecture=arch
        )

        if script:
            # Only reuse if we have a valid FleetDM script ID to execute
            if script.fleet_script_id:
                broadcast_log(job_id, agent_name,
                    f"[ScriptResolver] Result: FOUND (ID={script.registry_id}, "
                    f"filename={script.filename}, FleetDM={script.fleet_script_id})")
                broadcast_log(job_id, agent_name,
                    f"[ScriptResolver] Action: REUSE_EXISTING_SCRIPT → skipping research and generation")

                updates["script_registry_ids"][sig] = script.registry_id
                updates["script_hashes"][sig] = script.script_hash
                updates["risk_scores"][sig] = script.risk_score
                updates["risk_levels"][sig] = script.risk_level
                updates["risk_reasons_map"][sig] = script.risk_reasons

                updates["script_reused"][sig] = True
                updates["script_contents"][sig] = script.script_content or ""
                updates["fleet_script_ids"][sig] = script.fleet_script_id
                updates["current_script_type"][sig] = script.script_type

                AgentEventService.broadcast_risk(
                    job_id,
                    script.risk_score,
                    script.risk_level,
                    script.risk_reasons
                )
            else:
                # Script in DB but has no FleetDM ID — must re-upload or regenerate
                broadcast_log(job_id, agent_name,
                    f"[ScriptResolver] Result: FOUND in DB (ID={script.registry_id}) but no FleetDM script ID. "
                    f"Reason: script must be re-uploaded to FleetDM before reuse.")
                broadcast_log(job_id, agent_name,
                    f"[ScriptResolver] Action: RE_UPLOAD_REQUIRED")
                # We reuse the script content but need to re-upload — mark as not reused
                # so fleet_execution uploads it, but provide the content to skip generation
                updates["script_registry_ids"][sig] = script.registry_id
                updates["script_contents"][sig] = script.script_content or ""
                updates["script_hashes"][sig] = script.script_hash
                updates["risk_scores"][sig] = script.risk_score
                updates["risk_levels"][sig] = script.risk_level
                updates["risk_reasons_map"][sig] = script.risk_reasons
                updates["current_script_type"][sig] = script.script_type
                # script_reused = False so fleet_execution will re-upload it
                updates["script_reused"][sig] = False
        else:
            broadcast_log(job_id, agent_name,
                f"[ScriptResolver] Result: NOT_FOUND")
            broadcast_log(job_id, agent_name,
                f"[ScriptResolver] Action: RESEARCH_REQUIRED")

    updates["regeneration_count"] = state.get("regeneration_count", 0)
    updates["current_stage"] = "SCRIPT_GENERATION_REQUIRED"

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    return updates

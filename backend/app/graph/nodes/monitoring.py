import time
import asyncio
import os
import tempfile
from app.graph.state import InstallationState
from app.services.fleetdm_service import FleetDMService
from app.services.script_registry_service import ScriptRegistryService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log

async def monitor_execution(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "MonitoringAgent"
    stage_name = "EXECUTION_MONITORING"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting execution monitoring")
    
    applications = state.get("applications", [])
    updates = {"current_stage": "MONITORING", "execution_results": {}}
    
    if not settings.USE_FLEETDM:
        broadcast_log(job_id, agent_name, "DRY RUN - Monitoring skipped")
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        
        from app.api.routes.installation import ws_manager
        try:
            await ws_manager.broadcast_status(job_id, "COMPLETED", "Completed", 100)
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Broadcast failed: {e}", "warning")
            
        return {**updates, "status": "COMPLETED", "current_stage": "COMPLETED"}
        
    execution_ids = state.get("execution_ids", [])
    if not execution_ids:
        # If there are cached script failures recorded, this is a recoverable failure.
        # script_failure_analysis will detect cached_script_failures and trigger regeneration.
        cached_failures = state.get("cached_script_failures", {})
        if cached_failures:
            broadcast_log(job_id, agent_name,
                f"No execution IDs because cached script(s) failed pre-execution: {list(cached_failures.keys())}. "
                "Forwarding to failure analysis for recovery.", "warning")
            broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
            return {**updates, "status": "FAILED", "error_message": "Cached script execution failed."}
        
        error_message = "Missing execution IDs."
        broadcast_log(job_id, agent_name, "No execution IDs to monitor.", "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    host_ids = state.get("hosts_requiring_installation", state.get("host_ids", []))
    exec_to_host = {}
    for i, exec_id in enumerate(execution_ids):
        host_id = host_ids[i] if i < len(host_ids) else "Unknown"
        exec_to_host[exec_id] = host_id
        
    pending_executions = set(execution_ids)
    failed_executions = set()
    
    updates["status"] = "RUNNING"
    
    from app.api.routes.installation import ws_manager
    try:
        await ws_manager.broadcast_status(job_id, "RUNNING", "Installation", 50)
    except Exception as e:
        broadcast_log(job_id, agent_name, f"Broadcast failed: {e}", "warning")
    
    start_time = time.time()
    max_timeout = settings.SCRIPT_EXECUTION_TIMEOUT_SECONDS
    polling_interval = settings.SCRIPT_POLLING_INTERVAL
    
    current_attempts = state.get("current_attempts", {})
    maximum_attempts = state.get("maximum_attempts", {})
    current_script_types = state.get("current_script_type", {})
    
    os_groups = state.get("os_groups", {})
    host_to_sig = {}
    for sig, h_ids in os_groups.items():
        for h in h_ids:
            host_to_sig[h] = sig
    
    while pending_executions:
        elapsed = time.time() - start_time
        if elapsed > max_timeout:
            broadcast_log(job_id, agent_name, f"Execution monitoring timed out after {max_timeout} seconds.", "error")
            for exec_id in list(pending_executions):
                host_id = exec_to_host.get(exec_id)
                failed_executions.add(exec_id)
                if exec_id not in updates["execution_results"]:
                    updates["execution_results"][exec_id] = {}
                updates["execution_results"][exec_id]["host_timeout"] = True
                updates["execution_results"][exec_id]["output"] = "Execution timed out (15 minutes max)"
                try:
                    await ws_manager.broadcast_log(job_id, f"Script execution TIMED OUT (15 minutes) for Host {host_id}.")
                except Exception:
                    pass
            break
            
        for exec_id in list(pending_executions):
            host_id = exec_to_host.get(exec_id)
            sig = host_to_sig.get(host_id)
            
            attempt = current_attempts.get(sig, 1)
            max_attempt = maximum_attempts.get(sig, 1)
            script_type = current_script_types.get(sig, ".py")
            script_lang = "PowerShell" if script_type == ".ps1" else ("Bash" if script_type == ".sh" else "Python")
            
            broadcast_log(job_id, agent_name, f"Monitoring execution {exec_id} for Host {host_id}... (Elapsed: {int(elapsed)}s)")
            
            result = FleetDMService.get_script_result(exec_id)
            
            if result is None:
                broadcast_log(job_id, agent_name, f"FleetDM API unavailable or failed for execution {exec_id} (Host {host_id}). Will retry.", "warning")
                try:
                    await ws_manager.broadcast_log(job_id, f"Attempt: {attempt}/{max_attempt} | Script: {script_lang} | Execution ID: {exec_id} | Exit Code: RESULT_UNAVAILABLE | Elapsed: {int(elapsed)}s")
                except Exception:
                    pass
                continue
                
            exit_code = result.get("exit_code")
            output = result.get("output", "")
            
            updates["execution_results"][exec_id] = result
            
            try:
                exit_str = "null" if exit_code is None else str(exit_code)
                await ws_manager.broadcast_log(job_id, f"Attempt: {attempt}/{max_attempt} | Script: {script_lang} | Execution ID: {exec_id} | Exit Code: {exit_str} | Elapsed: {int(elapsed)}s")
            except Exception:
                pass
                
            if exit_code is not None or result.get("host_timeout"):
                if exit_code == 0:
                    broadcast_log(job_id, agent_name, f"Host {host_id} returned exit_code=0")
                    try:
                        await ws_manager.broadcast_log(job_id, f"Script execution finished with exit code 0 for Host {host_id}.")
                    except Exception:
                        pass
                else:
                    if result.get("host_timeout") or (output and "TimeoutExpired" in output):
                        broadcast_log(job_id, agent_name, f"Host {host_id} execution TIMEOUT", "warning")
                        try:
                            await ws_manager.broadcast_log(job_id, f"Script execution TIMED OUT for Host {host_id}.")
                        except Exception:
                            pass
                    elif result.get("host_offline"):
                        broadcast_log(job_id, agent_name, f"Host {host_id} execution HOST_OFFLINE", "error")
                    else:
                        broadcast_log(job_id, agent_name, f"Host {host_id} returned exit_code={exit_code} (SCRIPT_FAILURE)", "warning")
                        try:
                            await ws_manager.broadcast_log(job_id, f"Script execution failed for Host {host_id} with exit code {exit_code}.")
                        except Exception:
                            pass
                    failed_executions.add(exec_id)
                    
                active_app_name = state.get("application_name")
                if "DEPLOYIQ_RESULT_START" in output and "DEPLOYIQ_RESULT_END" in output:
                    result_block = output.split("DEPLOYIQ_RESULT_START")[1].split("DEPLOYIQ_RESULT_END")[0].strip()
                    parsed_app_name = None
                    parsed_inst_status = "UNKNOWN"
                    parsed_verif_status = "UNKNOWN"
                    parsed_version = None
                    
                    for line in result_block.split("\n"):
                        if "=" in line:
                            key, val = line.split("=", 1)
                            key = key.strip().upper()
                            val = val.strip()
                            if key == "APPLICATION":
                                parsed_app_name = val
                            elif key == "INSTALLATION_STATUS":
                                parsed_inst_status = val.upper()
                            elif key == "VERIFICATION_STATUS":
                                parsed_verif_status = val.upper()
                            elif key == "INSTALLED_VERSION":
                                parsed_version = val

                    if not parsed_app_name:
                        parsed_app_name = active_app_name

                    for app in applications:
                        if (app.get("name") == parsed_app_name or app.get("application_name") == parsed_app_name) and app.get("state") == "INSTALL_REQUIRED":
                            if parsed_app_name == active_app_name:
                                app["installation_status"] = parsed_inst_status
                                app["verification_status"] = parsed_verif_status
                                if parsed_version:
                                    app["installed_version"] = parsed_version
                                broadcast_log(job_id, agent_name, f"[{parsed_app_name}] Install: {parsed_inst_status}, Verify: {parsed_verif_status}")
                elif "DEPLOYIQ_INSTALL_RESULT:" in output:
                    result_block = output.split("DEPLOYIQ_INSTALL_RESULT:")[1].strip()
                    for line in result_block.split("\n"):
                        if "=" in line:
                            parsed_app_name, parsed_status = line.split("=", 1)
                            parsed_app_name = parsed_app_name.strip()
                            parsed_status = parsed_status.strip().upper()
                            for app in applications:
                                if (app.get("name") == parsed_app_name or app.get("application_name") == parsed_app_name) and app.get("state") == "INSTALL_REQUIRED":
                                    if parsed_app_name == active_app_name:
                                        app["installation_status"] = parsed_status
                                        broadcast_log(job_id, agent_name, f"[{parsed_app_name}] Installation status updated to {parsed_status}")
                else:
                    # Fallback if block is missing
                    fallback_status = "SUCCESS" if exit_code == 0 else "FAILED"
                    for app in applications:
                        if (app.get("name") or app.get("application_name")) == active_app_name:
                            app["installation_status"] = fallback_status
                            app["verification_status"] = "UNKNOWN"
                            broadcast_log(job_id, agent_name, f"[{app.get('name')}] Installation status fallback to {fallback_status}")
                            
                pending_executions.remove(exec_id)

        if pending_executions:
            await asyncio.sleep(polling_interval)

    # Determine overall status
    install_required_apps = [a for a in applications if a.get("state") == "INSTALL_REQUIRED"]
    success_count = sum(1 for a in install_required_apps if a.get("installation_status") in ["SUCCESS", "ALREADY_INSTALLED"] and a.get("verification_status") in ["SUCCESS", "UNKNOWN", "ALREADY_INSTALLED"])
    failed_count = sum(1 for a in install_required_apps if a.get("installation_status") in ["FAILED", "FAILURE"] or a.get("verification_status") in ["FAILED", "FAILURE"])
    
    if failed_count > 0 and success_count == 0:
        overall_status = "FAILED"
        broadcast_log(job_id, agent_name, "Overall deployment FAILED (all applications failed to install).", "error")
    elif failed_count > 0 and success_count > 0:
        overall_status = "PARTIAL_SUCCESS"
        broadcast_log(job_id, agent_name, "Overall deployment PARTIAL_SUCCESS (some applications failed, some succeeded).", "warning")
    else:
        overall_status = "SUCCESS"
        broadcast_log(job_id, agent_name, "Overall deployment SUCCESS (all applications installed successfully).")
        
    # Register successful new scripts
    script_reused_map = state.get("script_reused", {})
    script_contents = state.get("script_contents", {})
    fleet_script_ids = state.get("fleet_script_ids", {})
    if "script_registry_ids" not in updates:
        updates["script_registry_ids"] = state.get("script_registry_ids", {}).copy()
        
    for sig, h_ids in os_groups.items():
        if not script_reused_map.get(sig, False):
            # Check if execution was successful for this OS group
            sig_hosts = [h for h in h_ids if h in host_ids]
            if not sig_hosts:
                continue
                
            sig_success = True
            for exec_id, result in updates["execution_results"].items():
                if exec_to_host.get(exec_id) in sig_hosts:
                    if result.get("exit_code") != 0 or result.get("host_timeout"):
                        sig_success = False
                        break
                        
            if sig_success:
                # Also ensure the app didn't report a VERIFICATION failure in the payload
                active_app_name = state.get("application_name")
                active_app = next((a for a in applications if (a.get("name") == active_app_name or a.get("application_name") == active_app_name)), {})
                verification_failed = active_app.get("verification_status") in ["FAILED", "FAILURE"]
                
                if verification_failed:
                    broadcast_log(job_id, agent_name, f"[{sig}] Verification failed for one or more apps. Skipping script registry save.")
                else:
                    script_content = script_contents.get(sig)
                    script_id = fleet_script_ids.get(sig)
                    if script_content and script_id:
                        broadcast_log(job_id, agent_name, f"[{sig}] Execution and verification successful. Registering script to Script Registry.")
                    try:
                        os_name, arch = sig.split("_")
                        
                        active_app_name = state.get("application_name")
                        active_app = next((a for a in applications if (a.get("name") == active_app_name or a.get("application_name") == active_app_name)), {})
                        
                        combined_app_name = active_app_name
                        combined_version = active_app.get("installed_version") or active_app.get("target_version") or active_app.get("version", "latest")
                        
                        script_type = current_script_types.get(sig, ".py")
                        
                        # Upload to FleetDM with exact versioned name
                        exact_filename = ScriptRegistryService.generate_filename(combined_app_name, combined_version, script_type)
                        temp_dir = tempfile.mkdtemp()
                        exact_path = os.path.join(temp_dir, exact_filename)
                        
                        try:
                            with open(exact_path, "w") as f:
                                f.write(script_content)
                            upload_res = FleetDMService.upload_script(exact_path)
                            final_script_id = script_id # fallback to original if upload fails
                            
                            if upload_res and upload_res.get("script", {}).get("id"):
                                final_script_id = upload_res["script"]["id"]
                                # Clean up the original temp script used during execution
                                FleetDMService.delete_script(int(script_id))
                                broadcast_log(job_id, agent_name, f"[{sig}] Saved finalized script to FleetDM as {exact_filename} (ID: {final_script_id})")
                        finally:
                            try:
                                os.remove(exact_path)
                                os.rmdir(temp_dir)
                            except:
                                pass
                                
                        # Invalidate older versions in DB and FleetDM
                        old_fleet_ids = ScriptRegistryService.invalidate_old_versions(
                            application_name=combined_app_name,
                            current_version=combined_version,
                            operating_system=os_name,
                            architecture=arch
                        )
                        for old_id in old_fleet_ids:
                            FleetDMService.delete_script(old_id)
                            broadcast_log(job_id, agent_name, f"[{sig}] Deleted old version script {old_id} from FleetDM")
                        
                        registry_entry = ScriptRegistryService.save_script(
                            application_name=combined_app_name,
                            version=combined_version,
                            operating_system=os_name,
                            architecture=arch,
                            fleet_script_id=str(final_script_id),
                            script_hash=state.get("script_hashes", {}).get(sig),
                            risk_score=state.get("risk_scores", {}).get(sig),
                            risk_level=state.get("risk_levels", {}).get(sig),
                            risk_reasons=state.get("risk_reasons_map", {}).get(sig),
                            script_type=script_type,
                            script_content=script_content
                        )
                        updates["script_registry_ids"][sig] = registry_entry.registry_id
                    except Exception as e:
                        broadcast_log(job_id, agent_name, f"[{sig}] Failed to save to script registry: {e}", "warning")

    broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
    
    updates["applications"] = applications
    
    # We always return COMPLETED for the stage so it proceeds to cleanup & verification, 
    # but we update the graph status logic
    # In graph.py, it doesn't actually check state["status"] to route after monitoring, it always goes to cleanup.
    # We will just set the status to whatever it is, and downstream nodes will handle it.
    updates["fleet_execution_end_time"] = time.time()
    return {**updates, "status": overall_status, "current_stage": "COMPLETED"}

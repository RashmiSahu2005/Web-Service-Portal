import os
import tempfile
import json
import asyncio
from typing import Dict, Any

from app.services.fleetdm_service import FleetDMService
from app.core.config import settings
from app.graph.nodes.utils import broadcast_log

class VersionAvailabilityService:
    
    @classmethod
    def _generate_availability_script(cls, strategy: dict, version: str) -> str:
        installer_type = strategy.get("installer_type", "")
        package_name = strategy.get("package_name", "")
        
        return f"""#!/usr/bin/env python3
import subprocess
import json
import sys

def check():
    result = {{"status": "CHECK_FAILED"}}
    
    installer = "{installer_type}"
    pkg = "{package_name}"
    ver = "{version}"
    
    if not pkg:
        print(json.dumps({{"status": "NOT_AVAILABLE"}}))
        return
        
    try:
        if installer == "winget":
            cmd = ["winget", "show", "--id", pkg, "--version", ver, "--accept-source-agreements"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                result["status"] = "AVAILABLE"
            else:
                out = res.stdout + res.stderr
                if "No package found" in out:
                    result["status"] = "NOT_AVAILABLE"
                elif "is not recognized" in out:
                    result["status"] = "CHECK_FAILED"
                else:
                    # Generic failure
                    result["status"] = "CHECK_FAILED"
                    
        elif installer == "apt":
            cmd = ["apt-cache", "madison", pkg]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                if ver in res.stdout:
                    result["status"] = "AVAILABLE"
                else:
                    result["status"] = "NOT_AVAILABLE"
            else:
                result["status"] = "CHECK_FAILED"
                
        else:
            # Unsupported package manager for explicit version checks
            result["status"] = "CHECK_FAILED"
            
    except Exception as e:
        result["status"] = "CHECK_FAILED"
        
    print(json.dumps(result))

if __name__ == "__main__":
    check()
"""

    @classmethod
    async def _check_on_host(cls, host_id: int, script_id: str, job_id: str, agent_name: str) -> str:
        try:
            run_response = FleetDMService.run_script(host_id, script_id)
            if not run_response:
                return "CHECK_FAILED"
                
            exec_id = run_response.get("execution_id")
            if not exec_id:
                return "CHECK_FAILED"
                
            max_attempts = 15
            attempts = 0
            
            while attempts < max_attempts:
                await asyncio.sleep(settings.POLLING_INTERVAL)
                result = FleetDMService.get_script_result(exec_id)
                if not result:
                    return "CHECK_FAILED"
                    
                exit_code = result.get("exit_code")
                if exit_code is not None or result.get("host_timeout"):
                    if exit_code == 0:
                        output = result.get("output", "")
                        try:
                            parsed_json = json.loads(output)
                            return parsed_json.get("status", "CHECK_FAILED")
                        except Exception as e:
                            broadcast_log(job_id, agent_name, f"Failed to parse availability JSON on host {host_id}: {e}", "warning")
                            return "CHECK_FAILED"
                    return "CHECK_FAILED"
                
                attempts += 1
                
            broadcast_log(job_id, agent_name, f"Availability check script timed out on host {host_id}", "warning")
            return "CHECK_FAILED"
            
        except Exception as e:
            broadcast_log(job_id, agent_name, f"Error checking availability on host {host_id}: {e}", "error")
            return "CHECK_FAILED"

    @classmethod
    async def check_availability(cls, version: str, strategies: dict, os_groups: dict, job_id: str, agent_name: str) -> str:
        """
        Returns exactly one of: 'AVAILABLE', 'NOT_AVAILABLE', 'CHECK_FAILED'
        """
        if not settings.USE_FLEETDM:
            broadcast_log(job_id, agent_name, "DRY RUN - Mocking availability check as AVAILABLE")
            return "AVAILABLE"
            
        overall_status = "AVAILABLE"
        
        for sig, host_ids in os_groups.items():
            if not host_ids:
                continue
                
            strategy = strategies.get(sig)
            if not strategy:
                broadcast_log(job_id, agent_name, f"No strategy found for {sig}, returning CHECK_FAILED.", "warning")
                return "CHECK_FAILED"
                
            script_content = cls._generate_availability_script(strategy, version)
            
            fd, temp_path = tempfile.mkstemp(prefix="apphub_avail_check_", suffix=".py")
            script_id = None
            try:
                with os.fdopen(fd, 'w') as f:
                    f.write(script_content)
                response = FleetDMService.upload_script(temp_path)
                if response:
                    script_data = response.get("script", {})
                    script_id = script_data.get("id") or response.get("id") or response.get("script_id")
                    if script_id:
                        script_id = str(script_id)
            except Exception as e:
                broadcast_log(job_id, agent_name, f"Error uploading availability check script: {e}", "error")
                return "CHECK_FAILED"
            finally:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
                    
            if not script_id:
                broadcast_log(job_id, agent_name, f"Failed to upload availability script for {sig}.", "warning")
                return "CHECK_FAILED"
                
            # Check on the first host in the group
            host_id = host_ids[0]
            broadcast_log(job_id, agent_name, f"Checking availability of version {version} on host {host_id} ({sig})...")
            
            status = await cls._check_on_host(host_id, script_id, job_id, agent_name)
            
            if status == "CHECK_FAILED":
                return "CHECK_FAILED"
            elif status == "NOT_AVAILABLE":
                overall_status = "NOT_AVAILABLE"
                
        return overall_status

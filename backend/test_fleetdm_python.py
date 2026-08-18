import os
import time
import socket
from app.services.fleetdm_service import FleetDMService

def test_fleetdm_python():
    print("Testing FleetDM Python Execution...")
    
    hostname = socket.gethostname()
    host_id = FleetDMService.find_host(hostname)
    
    if not host_id:
        print(f"Could not find host {hostname} in FleetDM.")
        return
        
    print(f"Found host_id: {host_id}")
    
    timestamp = int(time.time())
    script_path = f"/tmp/test_fleet_python_{timestamp}.py"
    with open(script_path, "w") as f:
        f.write("#!/usr/bin/env python3\n")
        f.write("import sys\n")
        f.write("print('ApplicationHub Python FleetDM Test')\n")
        f.write("sys.exit(0)\n")
        
    print(f"Uploading script {script_path}...")
    upload_res = FleetDMService.upload_script(script_path)
    
    if not upload_res or "script_id" not in upload_res:
        print("Failed to upload script:", upload_res)
        return
        
    script_id = upload_res["script_id"]
    print(f"Uploaded script_id: {script_id}")
    
    print(f"Running script_id {script_id} on host_id {host_id}...")
    run_res = FleetDMService.run_script(host_id, script_id)
    
    if "execution_id" not in run_res:
        print("Failed to start execution:", run_res)
        return
        
    execution_id = run_res["execution_id"]
    print(f"Execution started, execution_id: {execution_id}")
    
    for _ in range(20):
        res = FleetDMService.get_script_result(execution_id)
        if not res:
            time.sleep(2)
            continue
            
        exit_code = res.get("exit_code")
        if exit_code is not None:
            print(f"Execution finished with exit_code: {exit_code}")
            print(f"Output: {res.get('output', '')}")
            return
            
        print("Still running...")
        time.sleep(2)
        
    print("Execution timed out.")

if __name__ == "__main__":
    test_fleetdm_python()

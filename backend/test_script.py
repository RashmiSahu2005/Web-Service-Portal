#!/usr/bin/env python3
import subprocess
import json
import sys

def check():
    result = {"installed_raw": None, "available_raw": None}
    
    installed_cmd = ["brave-browser", "--version"]
    if installed_cmd:
        try:
            res = subprocess.run(installed_cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                result["installed_raw"] = res.stdout.strip()
        except Exception:
            pass
            
    available_cmd = ["apt-cache", "policy", "brave-browser"]
    if available_cmd:
        try:
            res = subprocess.run(available_cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                result["available_raw"] = res.stdout.strip()
        except Exception:
            pass
            
    print(json.dumps(result))

if __name__ == "__main__":
    check()


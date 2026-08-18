import ast
import json
import re
from app.graph.state import InstallationState
from app.services.llm_service import LLMService
from app.services.agent_event_service import AgentEventService
from app.graph.nodes.utils import broadcast_stage, broadcast_log

def _perform_static_analysis(script: str, job_id: str, agent_name: str, script_type: str = ".py"):
    score = 0
    reasons = []
    is_high_risk = False
    
    dangerous_patterns = [
        (r"rm\s+-rf\s+/", "Contains destructive command (rm -rf /)", 100, True),
        (r"AWS_ACCESS_KEY_ID", "Contains potential AWS credentials", 100, True),
        (r"PASSWORD\s*=", "Contains potential hardcoded password", 80, True),
        (r"chmod\s+777", "Sets completely open permissions (chmod 777)", 80, True),
    ]
    
    for pattern, reason, penalty, high_risk in dangerous_patterns:
        if re.search(pattern, script, re.IGNORECASE):
            score += penalty
            reasons.append(reason)
            if high_risk:
                is_high_risk = True

    if script_type == ".py":
        try:
            tree = ast.parse(script)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        pass 
                
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr == 'run' and getattr(node.func.value, 'id', '') == 'subprocess':
                            has_shell_true = any(
                                kw.arg == 'shell' and isinstance(kw.value, ast.Constant) and kw.value.value is True
                                for kw in node.keywords
                            )
                            if has_shell_true:
                                score += 40
                                reasons.append("Uses subprocess.run with shell=True")
                            else:
                                score += 10
                                reasons.append("Uses subprocess.run")
                                
                        elif node.func.attr == 'system' and getattr(node.func.value, 'id', '') == 'os':
                            score += 50
                            reasons.append("Uses os.system")
                            
                        elif node.func.attr == 'rmtree' and getattr(node.func.value, 'id', '') == 'shutil':
                            score += 60
                            reasons.append("Uses shutil.rmtree for recursive deletion")
                            
        except SyntaxError:
            broadcast_log(job_id, agent_name, "Static analysis failed: Script contains syntax errors.", "warning")
            score += 100
            reasons.append("Script contains Python syntax errors")
            is_high_risk = True
    else:
        broadcast_log(job_id, agent_name, f"Skipping Python AST analysis for {script_type} script.")

    if "apt-get install" in script or "apt install" in script:
        pass # Normal package installation
    if "sources.list" in script or "add-apt-repository" in script:
        score += 10
        reasons.append("Modifies package repositories")
    if "curl " in script or "wget " in script:
        score += 10
        reasons.append("Downloads remote files (curl/wget)")
    if "reboot" in script or "shutdown" in script:
        score += 80
        reasons.append("Contains reboot or shutdown command")
        is_high_risk = True

    score = min(score, 100)
    return score, reasons, is_high_risk

def _perform_llm_analysis(script: str, job_id: str, agent_name: str, script_type: str = ".py"):
    lang_name = "Python" if script_type == ".py" else ("PowerShell" if script_type == ".ps1" else "Bash")
    prompt = f"""You are a strict security auditor. Analyze the following {lang_name} installation script for security risks.
Provide your response strictly in the following JSON format, and NOTHING ELSE:
{{
    "risk_score": <integer 0-100>,
    "reasons": ["<reason 1>", "<reason 2>"]
}}

Score Guidelines:
- 0-30 (LOW): Standard package installs (apt-get), importing official GPG keys, normal subprocess execution, running as root.
- 31-70 (MEDIUM): External repos, downloading remote scripts but verifying them, modifying /etc configuration for the app.
- 71-100 (HIGH): Destructive commands (rm -rf /), hardcoded secrets, shell=True with arbitrary variables, completely unknown remote binaries, curl | bash.

IMPORTANT RULES:
- DO NOT automatically classify an official package installer as HIGH just because it uses 'root', 'subprocess', or 'apt'.
- Evaluate INTENT. Official installation logic is LOW/MEDIUM.
- Only flag HIGH for genuinely dangerous operations.

Script to analyze:
```{lang_name.lower()}
{script}
```
"""
    try:
        response = LLMService.generate(prompt)
        match = re.search(r"```(?:json)?\n(.*?)```", response, re.DOTALL | re.IGNORECASE)
        if match:
            response = match.group(1).strip()
        
        data = json.loads(response)
        
        score = int(data.get("risk_score", 50))
        reasons = data.get("reasons", [])
        
        score = max(0, min(100, score))
        
        if not isinstance(reasons, list):
            reasons = ["LLM returned invalid reasons format"]
        else:
            reasons = [str(r) for r in reasons]
            
        return score, reasons
        
    except Exception as e:
        broadcast_log(job_id, agent_name, f"LLM risk analysis failed or returned invalid JSON: {e}", "warning")
        return 50, ["Failed to parse LLM security analysis"]

def analyze_risk(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "RiskAnalysisAgent"
    stage_name = "RISK_ANALYSIS"
    
    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")
    broadcast_log(job_id, agent_name, "Starting risk analysis")
    
    updates = {
        "current_stage": "RISK_ANALYZED",
        "risk_scores": state.get("risk_scores", {}),
        "risk_levels": state.get("risk_levels", {}),
        "risk_reasons_map": state.get("risk_reasons_map", {})
    }
    
    script_contents = state.get("script_contents", {})
    script_reused = state.get("script_reused", {})
    os_groups = state.get("os_groups", {})
    current_script_types = state.get("current_script_type", {})
    
    if not script_contents and not script_reused:
        error_message = "No scripts found to analyze."
        broadcast_log(job_id, agent_name, error_message, "error")
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
        return {**updates, "status": "FAILED", "error_message": error_message}
        
    max_final_score = 0
    max_level = "LOW"
    all_reasons_aggregated = set()
    has_high_risk = False
    
    for sig in os_groups.keys():
        if script_reused.get(sig):
            # Already analyzed
            score = updates["risk_scores"].get(sig, 0)
            level = updates["risk_levels"].get(sig, "LOW")
            reasons = updates["risk_reasons_map"].get(sig, [])
            
            max_final_score = max(max_final_score, score)
            if level == "HIGH":
                has_high_risk = True
                max_level = "HIGH"
            elif level == "MEDIUM" and max_level != "HIGH":
                max_level = "MEDIUM"
                
            all_reasons_aggregated.update(reasons)
            continue
            
        script = script_contents.get(sig)
        if not script:
            continue
            
        script_type = current_script_types.get(sig, ".py")
        broadcast_log(job_id, agent_name, f"Analysing generated {script_type} script for {sig}")
        
        static_score, static_reasons, static_is_high_risk = _perform_static_analysis(script, job_id, agent_name, script_type)
        llm_score, llm_reasons = _perform_llm_analysis(script, job_id, agent_name, script_type)
        
        final_score = max(static_score, llm_score)
        
        if static_is_high_risk:
            final_score = max(final_score, 75)
            
        all_reasons = list(set(static_reasons + llm_reasons))
        
        if final_score <= 30:
            level = "LOW"
        elif final_score <= 85:
            level = "MEDIUM"
        else:
            level = "HIGH"
            
        updates["risk_scores"][sig] = final_score
        updates["risk_levels"][sig] = level
        updates["risk_reasons_map"][sig] = all_reasons
        
        broadcast_log(job_id, agent_name, f"[{sig}] Risk Score: {final_score}, Level: {level}")
        
        max_final_score = max(max_final_score, final_score)
        if level == "HIGH":
            has_high_risk = True
            max_level = "HIGH"
        elif level == "MEDIUM" and max_level != "HIGH":
            max_level = "MEDIUM"
            
        all_reasons_aggregated.update(all_reasons)

    all_reasons_aggregated = list(all_reasons_aggregated)
    
    AgentEventService.broadcast_risk(
        job_id,
        max_final_score,
        max_level,
        all_reasons_aggregated
    )
        
    if has_high_risk:
        broadcast_log(job_id, agent_name, "HIGH RISK script detected in one or more OS groups. Blocking execution.", "warning")
        updates["status"] = "BLOCKED_HIGH_RISK"
        updates["error_message"] = "HIGH risk script generated by LLM."
        broadcast_stage(job_id, agent_name, stage_name, "BLOCKED")
    else:
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        
    return updates

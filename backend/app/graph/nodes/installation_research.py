"""
installation_research.py
------------------------
LangGraph node: INSTALLATION_RESEARCH

Runs between SCRIPT_REGISTRY_LOOKUP and SCRIPT_GENERATION when no cached script
exists for one or more OS groups.

Responsibilities:
  - Determine which OS groups need fresh research (script_reused=False)
  - Call InstallationResearchService for each such group
  - Merge the resulting InstallationStrategy into state["strategies"][sig][app_name]
    (the exact dict key already consumed by script_generation._build_prompt())
  - Broadcast INSTALLATION_RESEARCH stage events and research_result WS event
  - On retry: bypass research cache and include failure_context in research call
  - Skip silently for OS groups where script_reused=True (fast-path preserved)

Does NOT generate scripts. Does NOT modify FleetDM state.
"""

from app.core.config import settings
from app.graph.nodes.utils import broadcast_stage, broadcast_log
import time
from app.graph.state import InstallationState
from app.services.agent_event_service import AgentEventService
from app.services.installation_research_service import InstallationResearchService
from app.services.web_search_service import WebSearchService


def installation_research(state: InstallationState) -> dict:
    job_id = state.get("job_id", "")
    agent_name = "InstallationResearchAgent"
    stage_name = "INSTALLATION_RESEARCH"

    broadcast_stage(job_id, agent_name, stage_name, "RUNNING")

    app_name = state.get("application_name", "Unknown")
    target_version = state.get("target_version", "latest")
    os_groups = state.get("os_groups", {})
    script_reused = state.get("script_reused", {})
    operation = state.get("operation", "INSTALL")
    
    research_start_time = state.get("research_start_time")
    if not research_start_time:
        research_start_time = time.time()

    # ── Check if research is globally disabled ───────────────────────────────
    if not settings.INSTALLATION_RESEARCH_ENABLED:
        broadcast_log(
            job_id, agent_name,
            "Installation research is disabled (INSTALLATION_RESEARCH_ENABLED=false). Skipping."
        )
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        return {"research_skipped": {sig: True for sig in os_groups}}

    # ── Initialise return state ──────────────────────────────────────────────
    existing_strategies = {
        sig: dict(per_sig) for sig, per_sig in (state.get("strategies") or {}).items()
    }
    research_results: dict = dict(state.get("research_results") or {})
    research_skipped: dict = {}

    # ── SearXNG health check (once per invocation, non-blocking) ─────────────
    if not WebSearchService.health_check():
        broadcast_log(
            job_id, agent_name,
            "[DeployIQ][InstallationResearch] WARNING: SearXNG is unreachable or JSON format "
            "is disabled. Script generation will proceed without web-search evidence. "
            f"Verify your SearXNG instance at {settings.SEARXNG_BASE_URL} has JSON enabled.",
            "warning",
        )
        # Continue without search — LLM will use its own knowledge
        # but we must still set up strategy placeholders

    failure_context_map = state.get("script_failure_context") or {}
    
    research_attempts = dict(state.get("research_attempts") or {})
    max_research_attempts = dict(state.get("max_research_attempts") or {})
    
    worst_status = "RESEARCH_SUCCESS"
    error_message = None

    # ── Research per OS group ─────────────────────────────────────────────────
    for sig in os_groups.keys():
        if script_reused.get(sig, False):
            broadcast_log(
                job_id, agent_name,
                f"[{sig}] Script reused from registry — skipping installation research."
            )
            research_skipped[sig] = True
            continue

        research_skipped[sig] = False
        os_parts = sig.split("_")
        os_name = os_parts[0] if os_parts else sig
        architecture = os_parts[-1] if len(os_parts) > 1 else "unknown"

        # Read current attempt number (1-indexed), then immediately increment it
        # so the next invocation sees attempt+1 even if state is re-entered.
        attempt = research_attempts.get(sig, 0) + 1
        research_attempts[sig] = attempt  # persist the incremented value
        max_attempts = max_research_attempts.get(sig, 3)  # default 3
        
        if attempt > max_attempts:
            broadcast_log(job_id, agent_name, f"[{sig}] Max research attempts ({max_attempts}) reached. Failing.", "error")
            worst_status = "FAILED"
            error_message = f"Max research attempts ({max_attempts}) reached."
            research_results[sig] = {"research_status": "FAILED", "error": error_message}
            continue
            
        failure_context = failure_context_map.get(sig)
        bypass_cache = attempt > 1 or bool(failure_context)  # always bypass cache on retry

        sig_hosts = os_groups.get(sig, [])
        all_constraints = state.get("host_constraints") or {}
        group_constraints = {}
        for h_id in sig_hosts:
            if h_id in all_constraints:
                group_constraints.update(all_constraints[h_id])

        # Find current version for this OS group
        current_version = ""
        for h_id in sig_hosts:
            installed = state.get("installed_versions", {}).get(h_id, {}).get(app_name)
            if installed:
                current_version = installed
                break
                
        # Find installation method for this OS group
        installation_method = existing_strategies.get(sig, {}).get(app_name, {}).get("package_manager") or \
                              existing_strategies.get(sig, {}).get(app_name, {}).get("installation_method", "")
                              
        broadcast_log(
            job_id, agent_name,
            f"[DeployIQ][InstallationResearch] "
            f"Application={app_name} Version={target_version} Operation={operation} "
            f"OS={os_name} Architecture={architecture} Research Attempt={attempt}/{max_attempts}"
        )

        try:
            strategy = InstallationResearchService.research(
                application=app_name,
                version=target_version,
                os_name=os_name,
                architecture=architecture,
                attempt=attempt,
                host_constraints=group_constraints if group_constraints else None,
                failure_context=failure_context,
                bypass_cache=bypass_cache,
                operation=operation,
                current_version=current_version,
                installation_method=installation_method
            )
        except Exception as exc:
            import traceback
            tb = traceback.format_exc()
            broadcast_log(
                job_id, agent_name,
                f"[{sig}] Error during installation research: {exc}\n{tb}",
                "error",
            )
            research_results[sig] = {"research_status": "RESEARCH_ERROR", "error": str(exc)}
            worst_status = "RESEARCH_ERROR"
            error_message = str(exc)
            continue

        strategy_dict = strategy.model_dump()
        research_results[sig] = strategy_dict

        # ── Merge into state["strategies"][sig][app_name] ────────────────────
        # This is the exact dict key that _build_prompt() in script_generation.py
        # already reads, so no structural change to script generation is needed.
        if sig not in existing_strategies:
            existing_strategies[sig] = {}
        existing_strategies[sig][app_name] = strategy_dict

        # ── Log summary ──────────────────────────────────────────────────────
        broadcast_log(
            job_id, agent_name,
            f"[DeployIQ][InstallationResearch] "
            f"RecommendedMethod={strategy.recommended_method!r} "
            f"Confidence={strategy.confidence:.2f} "
            f"Sources={len(strategy.source_urls)}"
        )
        if getattr(strategy, "notes", None):
            for w in strategy.notes:
                broadcast_log(job_id, agent_name, f"[{sig}] NOTE: {w}")

        if strategy.research_status == "RESEARCH_INSUFFICIENT":
            broadcast_log(
                job_id, agent_name,
                f"[{sig}] Research status=RESEARCH_INSUFFICIENT. Missing critical evidence.",
                "warning",
            )
            if worst_status != "RESEARCH_ERROR":
                worst_status = "RESEARCH_INSUFFICIENT"
        elif strategy.research_status == "RESEARCH_ERROR":
            if worst_status != "RESEARCH_ERROR":
                worst_status = "RESEARCH_ERROR"

        # ── Broadcast to frontend ─────────────────────────────────────────────
        AgentEventService.broadcast_research_result(
            job_id=job_id,
            application=app_name,
            recommended_method=strategy.recommended_method,
            confidence=strategy.confidence,
            sources_count=len(strategy.source_urls),
            sources=strategy.source_urls,
            warnings=strategy.notes,
            attempt=attempt,
        )

    # ── Handle status and return ──────────────────────────────────────────────
    if worst_status != "RESEARCH_SUCCESS":
        broadcast_stage(job_id, agent_name, stage_name, "FAILED")
    else:
        broadcast_stage(job_id, agent_name, stage_name, "COMPLETED")
        
    return {
        "strategies": existing_strategies,
        "research_results": research_results,
        "research_skipped": research_skipped,
        "research_attempts": research_attempts,
        "research_start_time": research_start_time,
        "research_end_time": time.time(),
        "status": worst_status,
        "error_message": error_message,
    }

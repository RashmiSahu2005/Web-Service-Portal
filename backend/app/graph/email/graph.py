# pyrefly: ignore [missing-import]
from langgraph.graph import StateGraph, END
from app.graph.email.state import EmailState
from app.graph.email.nodes.intent_classifier import classify_intent
from app.graph.email.nodes.validation import validate_request
from app.graph.email.nodes.approval_gate import check_approval_gate
from app.graph.email.nodes.request_mapping import map_to_installation

def route_after_classifier(state: EmailState):
    if state.get("status") in ["INVALID", "REJECTED"]: return "END"
    return "validation"

def route_after_validation(state: EmailState):
    if state.get("status") in ["INVALID", "REJECTED"]: return "END"
    return "approval_gate"

def route_after_approval(state: EmailState):
    status = state.get("status")
    if status == "APPROVED":
        return "request_mapping"
    # If PENDING_APPROVAL, we stop here and wait for reply.
    # If REJECTED or INVALID, we also stop.
    return "END"

def create_email_intake_graph():
    workflow = StateGraph(EmailState)
    
    workflow.add_node("intent_classifier", classify_intent)
    workflow.add_node("validation", validate_request)
    workflow.add_node("approval_gate", check_approval_gate)
    workflow.add_node("request_mapping", map_to_installation)
    
    workflow.set_entry_point("intent_classifier")
    
    workflow.add_conditional_edges("intent_classifier", route_after_classifier, {
        "END": END,
        "validation": "validation"
    })
    
    workflow.add_conditional_edges("validation", route_after_validation, {
        "END": END,
        "approval_gate": "approval_gate"
    })
    
    workflow.add_conditional_edges("approval_gate", route_after_approval, {
        "END": END,
        "request_mapping": "request_mapping"
    })
    
    workflow.add_edge("request_mapping", END)
    
    return workflow.compile()

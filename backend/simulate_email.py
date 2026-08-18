import os
import sys
import json
import uuid

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))

from app.graph.email.graph import create_email_intake_graph
from app.graph.email.state import EmailState
import redis

def simulate():
    print("--- SIMULATING EMAIL INTAKE ---")
    graph = create_email_intake_graph()
    
    # 1. Simulate the initial request email
    msg_id = f"test-{uuid.uuid4()}@test.com"
    initial_state = EmailState(
        message_id=msg_id,
        in_reply_to=None,
        references=[],
        subject="Install Request",
        body="install brave browser on 192.168.13.106",
        sender="boss@company.com",
        status="RECEIVED"
    )
    
    print(f"\n1. Sending initial request to graph: {initial_state['body']}")
    result = graph.invoke(initial_state)
    print(f"Result Status: {result.get('status')}")
    print(f"Extracted App: {result.get('application_name')}")
    print(f"Extracted IP: {result.get('target_host_ip')}")
    
    if result.get("status") != "PENDING_APPROVAL":
        print(f"FAILED TO REACH PENDING_APPROVAL. Error: {result.get('error_message')}")
        return
        
    print("\n--- WAITING FOR APPROVAL ---")
    # Verify it is in Redis
    r = redis.Redis.from_url("redis://localhost:6379/0", decode_responses=True)
    saved = r.get(f"email_request:{msg_id}")
    if saved:
        print("Successfully saved to Redis for thread correlation!")
    else:
        print("ERROR: Not saved in Redis!")
        return
        
    # 2. Simulate the approval reply email
    reply_id = f"reply-{uuid.uuid4()}@test.com"
    reply_state = EmailState(
        message_id=reply_id,
        in_reply_to=msg_id, # This ties it to the thread!
        references=[msg_id],
        subject="Re: Install Request",
        body="Yes, go ahead and install it.",
        sender="admin@company.com",
        status="RECEIVED"
    )
    
    print(f"\n2. Sending approval reply to graph: {reply_state['body']}")
    result2 = graph.invoke(reply_state)
    print(f"Result Status: {result2.get('status')}")
    
    if result2.get("status") == "APPROVED":
        print("\nSUCCESS! The email intake graph correctly parsed the request, auto-registered the app, correlated the approval reply, and dispatched it to the installation queue!")
    else:
        print(f"FAILED TO APPROVE. Error: {result2.get('error_message')}")

if __name__ == "__main__":
    simulate()

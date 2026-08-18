import sys
import os

# Add backend to path so imports work if run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from app.graph.graph import create_installation_graph

def print_graph_structure():
    graph = create_installation_graph()
    print("========================================")
    print("LANGGRAPH ARCHITECTURE TOPOLOGY")
    print("========================================")
    graph.get_graph().print_ascii()
    print("========================================")

if __name__ == "__main__":
    print_graph_structure()

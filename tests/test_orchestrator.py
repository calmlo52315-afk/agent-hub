
from runtime.orchestrator import Orchestrator
import sys

print("Loading orchestrator...")
orch = Orchestrator.load()
print("Orchestrator loaded!")

instruction = "Write 'Hello, World!' to demo_workspace/test.txt"
print(f"Running instruction: {instruction}")
result = orch.run_task(instruction=instruction)
print("\nResult:", result)
print("\nDone!")

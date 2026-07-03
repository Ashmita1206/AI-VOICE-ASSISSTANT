import sys
from agentic.llm.fallback import apply_heuristic_fallback
from execution.executor import DesktopExecutor
from agentic.schemas import ExecutionPlan, ActionStep

def main():
    query = "try sending a 'Hi!' msg to harshita frommy contacts in whatsapp"
    print("=" * 60)
    print(f"JARVIS AI DESKTOP AGENT - LIVE TEST RUN")
    print("=" * 60)
    print(f"Executing command: \"{query}\"\n")
    
    # 1. Plan using fallback heuristics
    planner_output = apply_heuristic_fallback(query)
    print(f"🧠 Intent Detected: {planner_output.intent}")
    print(f"📋 Steps to execute:")
    for i, s in enumerate(planner_output.steps, 1):
        print(f"  {i}. {s.tool} with arguments: {s.args}")
        
    # 2. Decompose to ExecutionPlan
    plan_steps = [ActionStep(tool=s.tool, args=s.args) for s in planner_output.steps]
    plan = ExecutionPlan(
        thought=planner_output.reasoning,
        steps=plan_steps,
        response=""
    )
    
    # 3. Execute!
    print("\n⚙ Starting execution...")
    executor = DesktopExecutor()
    results = executor.execute(plan)
    
    print("\n✅ Execution Finished!")
    print("=" * 60)

if __name__ == "__main__":
    main()

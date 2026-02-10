"""
Game Agent - Main Loop
Connects Orchestrator (Pro) and Executor (Flash) into a complete agent.
"""

# Load environment first
from dotenv import load_dotenv
load_dotenv()

import json
import re
import time
import pydirectinput

from orchestrator import Orchestrator
from executor import Executor


# ============================================================================
# GAME CONTEXT PRESETS
# ============================================================================

TERRARIA_CONTEXT = """
You are operating in Terraria, a 2D side-view, tile-based sandbox world with gravity.
The player can move left/right, jump, and use tools with the mouse.
Most terrain blocks are destructible.

WORLD STRUCTURE:
- The world has a surface and underground layers beneath it.
- Visibility underground is limited by darkness; light sources (torches) are required to see.
- Underground caves become more common with depth.

CAVES:
- A cave is a naturally generated underground space with open air tunnels or chambers.
- Caves may contain vertical shafts, horizontal tunnels, and branching paths.
- caves can be reached by digging downward using a pickaxe.
- Digging straight down or diagonally will eventually intersect underground cave systems.

CONTROLS:
- A: Move left
- D: Move right
- Space: Jump, Hold Space to jump higher
- Left-click: Use equipped tool (pickaxe, sword, torch placement, etc.), Hold Left click to break with pickaxe
- E: Open inventory
- 1-9: Select hotbar slot
- Esc: Open menu

RELEVANT ACTIONS:
- Use a pickaxe to dig through dirt or stone (left-click on blocks), you can only break blocks that you are literally right next to, so go as close as possible before breaking.
- Place torches to see while underground.
- Move cautiously when descending, as caves often contain vertical drops.

Assume digging is always possible. The world is procedurally generated and there is always
underground space below the surface.
"""


class GameAgent:
    """
    Complete game-playing agent.
    
    Two modes of operation:
    - General tasks (navigation, mining, etc.): Uses Orchestrator (Pro) + Executor (Flash)
      with screenshot-based perception and basic tool calls.
    - Combat tasks (boss fights, etc.): Routes to CombatLearner for real-time tracking,
      script generation, and iterative improvement from fight footage.
    """
    
    def __init__(self, pro_model: str = "gemini-3-pro-preview", flash_model: str = "gemini-3-flash-preview"):
        """
        Initialize the game agent.
        
        Args:
            pro_model: Model for orchestration (planning, diagnosis)
            flash_model: Model for execution (subtask attempts)
        """
        self.orchestrator = Orchestrator(model=pro_model)
        self.executor = Executor(model=flash_model)
        self.pro_model = pro_model
    
    def _is_combat_task(self, goal: str) -> bool:
        """Check if a goal requires the real-time combat system."""
        combat_keywords = ["defeat", "fight", "kill", "boss", "battle", "combat", "slay"]
        return any(kw in goal.lower() for kw in combat_keywords)
    
    def _extract_enemy_name(self, goal: str) -> str:
        """Try to extract an enemy name from the goal string.
        
        Looks for patterns like 'defeat the Empress of Light' or 'fight King Slime'.
        Falls back to the full goal string if no pattern matches.
        """
        # Try to find "defeat/fight/kill the <enemy name>"
        match = re.search(r'(?:defeat|fight|kill|battle|slay)\s+(?:the\s+)?(.+)', goal, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return goal
    
    def run(self, goal: str, game_context: str = None, enemy_video: str = None, enemy_name: str = None) -> dict:
        """
        Run the agent to complete a goal.
        
        Automatically detects combat tasks and routes to the appropriate system:
        - Combat tasks (with enemy_video): Uses CombatLearner for real-time fights
        - General tasks: Uses Orchestrator + Executor with screenshots
        
        Args:
            goal: High-level objective (e.g., "Find iron ore" or "Defeat the Empress of Light")
            game_context: Optional info about current game state or player kit
            enemy_video: Path to enemy footage (triggers combat mode)
            enemy_name: Explicit enemy name (auto-extracted from goal if not provided)
        
        Returns:
            Dictionary with final status and history of attempts.
        """
        print(f"\n{'='*60}")
        print(f"GOAL: {goal}")
        print(f"{'='*60}\n")
        
        # Route combat tasks to the CombatLearner
        if self._is_combat_task(goal) and enemy_video:
            from combat_learner import CombatLearner
            
            resolved_name = enemy_name or self._extract_enemy_name(goal)
            print(f"[AGENT] Combat task detected. Enemy: {resolved_name}")
            print(f"[AGENT] Routing to CombatLearner...\n")
            
            learner = CombatLearner(model=self.pro_model)
            return learner.learn_to_fight(
                enemy_name=resolved_name,
                enemy_video_path=enemy_video,
                enemy_context=game_context or "",
            )
        
        # --- General task flow (existing Orchestrator + Executor) ---
        
        # Step 1: Capture current game state and plan
        print("[ORCHESTRATOR] Capturing current game state...")
        from screenshot import capture_screenshot
        planning_screenshot = capture_screenshot()
        print(f"[ORCHESTRATOR] Screenshot captured: {len(planning_screenshot)//1024}KB")
        
        print("[ORCHESTRATOR] Planning goal...")
        plan = self.orchestrator.plan(goal, game_context, screenshot=planning_screenshot)
        
        if "error" in plan:
            print(f"[ERROR] Failed to create plan: {plan}")
            return {"status": "failed", "error": "Planning failed", "plan": plan}
        
        print(f"[ORCHESTRATOR] Created {len(plan.get('subtasks', []))} subtasks:")
        for st in plan.get("subtasks", []):
            print(f"  {st['id']}. {st['description']}")
        
        # Context search disabled - using user-provided game_context instead
        # The google_search was returning "I can't access your game" responses
        # if plan.get("context_needed"):
        #     print(f"\n[ORCHESTRATOR] Searching for context...")
        #     search_query = plan["context_needed"]
        #     if game_context:
        #         search_query = f"{game_context} - {search_query}"
        #     context = self.orchestrator.google_search(search_query)
        #     print(f"[CONTEXT] {context[:200]}...")
        
        # Step 2: Execute each subtask
        history = []
        
        for subtask in plan.get("subtasks", []):
            print(f"\n{'─'*40}")
            print(f"[SUBTASK {subtask['id']}] {subtask['description']}")
            print(f"[CRITERIA] {subtask['success_criteria']}")
            print(f"{'─'*40}")
            
            # Register any new tools needed
            for tool_name in subtask.get("tools_needed", []):
                if tool_name not in self.executor.tool_registry:
                    print(f"[ORCHESTRATOR] Creating new tool: {tool_name}")
                    tool_code = self.orchestrator.request_tool(
                        f"A tool called '{tool_name}' for game automation"
                    )
                    self._register_dynamic_tool(tool_name, tool_code)
            
            # Attempt the subtask
            print(f"\n[EXECUTOR] Attempting subtask...")
            result = self.executor.attempt_subtask(subtask)
            
            history.append({
                "subtask": subtask,
                "result": result
            })
            
            print(f"[EXECUTOR] Status: {result['status']}")
            print(f"[EXECUTOR] Attempts: {result['attempts']}")
            
            # Handle result
            if result["status"] == "done":
                print(f"[SUCCESS] Subtask completed!")
                continue
            
            elif result["status"] == "stuck":
                print(f"[STUCK] {result['message']}")
                
                # Pro diagnoses the failure
                if result.get("final_video"):
                    print(f"\n[ORCHESTRATOR] Diagnosing failure...")
                    diagnosis = self.orchestrator.diagnose_failure(
                        subtask,
                        result["final_video"],
                        result["message"]
                    )
                    print(f"[DIAGNOSIS] {diagnosis.get('diagnosis', 'Unknown')}")
                    
                    if diagnosis.get("needs_new_tool"):
                        print(f"[ORCHESTRATOR] Creating new tool: {diagnosis['new_tool_description']}")
                        # Would create and retry here
                    
                    if diagnosis.get("retry_with_modifications"):
                        print(f"[ORCHESTRATOR] Suggested retry: {diagnosis['retry_with_modifications']}")
                        # Would retry with modifications here
                
                # For now, continue to next subtask
                print("[AGENT] Moving to next subtask...")
            
            elif result["status"] == "max_attempts":
                print(f"[FAILED] Max attempts reached")
                print("[AGENT] Moving to next subtask...")
        
        # Final summary
        print(f"\n{'='*60}")
        print("AGENT RUN COMPLETE")
        print(f"{'='*60}")
        
        successful = sum(1 for h in history if h["result"]["status"] == "done")
        total = len(history)
        print(f"Completed: {successful}/{total} subtasks")
        
        return {
            "status": "completed" if successful == total else "partial",
            "successful_subtasks": successful,
            "total_subtasks": total,
            "history": history
        }
    
    def _register_dynamic_tool(self, name: str, code: str):
        """Register a dynamically created tool."""
        # DEBUG: Print the generated code
        print(f"\n[DEBUG] Generated code for '{name}':")
        print("─" * 40)
        print(code)
        print("─" * 40)
        
        namespace = {
            'pydirectinput': pydirectinput,
            'time': time
        }
        
        try:
            exec(code, namespace)
            
            # Extract function name from code
            func_match = re.search(r"def\s+([a-zA-Z_]\w*)\s*\(", code)
            if func_match:
                actual_name = func_match.group(1)
                self.executor.register_tool(name, namespace[actual_name])
                print(f"[TOOLS] Registered: {name}")
            else:
                print(f"[ERROR] Could not parse function from code")
        except Exception as e:
            print(f"[ERROR] Failed to register tool: {e}")


if __name__ == "__main__":
    import argparse
    
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Game Agent - AI that plays games")
    parser.add_argument(
        "--goal", "-g", required=True,
        help="High-level objective (e.g. 'Defeat the Empress of Light' or 'Dig down to find a cave')"
    )
    parser.add_argument(
        "--video", "-v", default=None,
        help="Path to enemy footage (triggers combat mode for boss fights)"
    )
    parser.add_argument(
        "--enemy", "-e", default=None,
        help="Explicit enemy name (auto-extracted from goal if not provided)"
    )
    parser.add_argument(
        "--context", "-c", default=None,
        help="Game context or player kit description"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("GAME AGENT")
    print("=" * 60)
    print(f"\nGoal: {args.goal}")
    if args.video:
        print(f"Enemy video: {args.video}")
    print("\nMake sure your game is open and focused!")
    
    input("\nPress Enter when ready to start...")
    time.sleep(2)  # Give time to focus game window
    
    agent = GameAgent()
    
    # Use provided context, or fall back to Terraria context for general tasks
    context = args.context or (TERRARIA_CONTEXT if not args.video else "")
    
    result = agent.run(
        goal=args.goal,
        game_context=context,
        enemy_video=args.video,
        enemy_name=args.enemy,
    )
    
    print("\n" + "=" * 60)
    print("FINAL RESULT:")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2))

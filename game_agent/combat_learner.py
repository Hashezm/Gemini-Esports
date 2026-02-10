"""
Combat Learner - Automated fight-analyze-improve loop.

Given an enemy name and a video of the enemy, this module:
1. Extracts a static sprite reference for real-time tracking
2. Starts the tracker service so game_state has live boss positions
3. Uses Gemini Pro to generate an initial combat script from the video
4. Runs the script in-game while recording the fight
5. Sends the fight recording back to Gemini for analysis
6. Gets an improved script and repeats until victory or max attempts

Usage:
    python combat_learner.py --enemy "Empress of Light" --video videos/empressoflight.mp4
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import importlib.util
import os
import re
import tempfile
import threading
import time

from google import genai
from google.genai import types

from game_state import game_state
from actions import actions
from screen_recorder import ScreenRecorder
from script_runner import load_script_from_path, run_script_timed
from tracker_service import create_tracker_from_extraction_dir
from static_element_extraction_pipeline import run_pipeline as run_extraction_pipeline


class CombatLearner:
    """
    Automated combat learning system.
    
    Uses Gemini Pro to iteratively write and improve combat scripts
    based on real fight footage. The AI watches itself fail, figures
    out what went wrong, and writes a better strategy each time.
    """
    
    def __init__(self, model: str = "gemini-3-pro-preview"):
        self.client = genai.Client()
        self.model = model
        
        # How long the boss must be gone before we consider the fight over
        self.boss_gone_threshold = 15  # seconds
        # Hard timeout per fight attempt (safety net)
        self.fight_timeout = 180  # seconds (3 minutes)
        # FPS for the script runner during fights
        self.fight_fps = 30
        # FPS for screen recording (sent to Gemini for analysis)
        self.recording_fps = 10
        
        # Paths
        self.base_dir = os.path.dirname(__file__)
        self.scripts_dir = os.path.join(self.base_dir, "test_scripts")
        self.videos_dir = os.path.join(self.scripts_dir, "fightvideos")
        self.extraction_dir = os.path.join(self.base_dir, "extraction_stuff")
        
        os.makedirs(self.videos_dir, exist_ok=True)
    
    # =========================================================
    # MAIN ENTRY POINT
    # =========================================================
    
    def learn_to_fight(
        self,
        enemy_name: str,
        enemy_video_path: str,
        max_attempts: int = 10,
        enemy_context: str = "",
    ) -> dict:
        """
        Full automated pipeline: extract sprite, track enemy, generate scripts,
        fight, analyze, improve, repeat until victory.
        
        Args:
            enemy_name: Display name of the enemy (e.g. "Empress of Light")
            enemy_video_path: Path to a video showing the enemy in action
            max_attempts: Max fight attempts before giving up
            enemy_context: Extra context about player kit, weapons, etc.
        
        Returns:
            Dict with status, winning_script (if won), attempt count, and history.
        """
        print(f"\n{'='*60}")
        print(f"COMBAT LEARNER: {enemy_name}")
        print(f"Video: {enemy_video_path}")
        print(f"Max attempts: {max_attempts}")
        print(f"{'='*60}\n")
        
        # Sanitized name for file paths (e.g. "empress_of_light")
        safe_name = re.sub(r'[^\w\-]', '_', enemy_name).lower()
        # Keyword to match in game_state entity names (lowercase)
        enemy_keyword = enemy_name.split()[0].lower()  # e.g. "empress"
        
        tracker = None
        history = []
        
        try:
            # --- Phase 1: Ensure we have a reference sprite for tracking ---
            reference_path = os.path.join(self.extraction_dir, safe_name, "reference_crop.png")
            
            if os.path.exists(reference_path):
                print(f"[EXTRACT] Reference crop already exists: {reference_path}")
            else:
                print(f"[EXTRACT] No reference crop found. Running extraction pipeline...")
                result = run_extraction_pipeline(enemy_video_path, enemy_name)
                if result is None:
                    return {"status": "failed", "error": "Extraction pipeline failed to produce a reference crop", "attempts": 0, "history": []}
                reference_path = result
                print(f"[EXTRACT] Reference crop saved: {reference_path}")
            
            # --- Phase 2: Start the tracker service ---
            print(f"\n[TRACKER] Starting real-time tracker...")
            tracker = create_tracker_from_extraction_dir(
                extraction_dir=self.extraction_dir,
                confidence=0.85,
                downscale_factor=0.5,
                skip_full_scan=True,
            )
            tracker.start()
            time.sleep(0.5)  # Let the tracker warm up
            print(f"[TRACKER] Running")
            
            # --- Phase 3: Create Gemini chat with the system prompt ---
            system_prompt = self._build_system_prompt(enemy_name, enemy_context)
            config = {"system_instruction": [system_prompt]}
            
            chat = self.client.chats.create(model=self.model, config=config)
            print(f"[GEMINI] Chat session created (model: {self.model})")
            
            # --- Phase 4: Generate the initial combat script ---
            print(f"\n[GEMINI] Uploading enemy analysis video...")
            video_file = self._upload_video(enemy_video_path)
            
            print(f"[GEMINI] Requesting initial combat script...")
            response = chat.send_message([
                types.Part(
                    file_data=types.FileData(file_uri=video_file.uri),
                    video_metadata=types.VideoMetadata(fps=20)
                ),
                f"Here is footage of the {enemy_name}. Analyze its attack patterns and movement, "
                f"then write a combat script to defeat it."
            ])
            
            script_code = self._parse_script(response.text)
            if script_code is None:
                return {"status": "failed", "error": "Gemini did not return a valid script", "attempts": 0, "history": []}
            
            print(f"[GEMINI] Initial script received ({len(script_code)} chars)")
            
            # --- Phase 5: Fight loop ---
            for attempt in range(1, max_attempts + 1):
                print(f"\n{'='*60}")
                print(f"ATTEMPT {attempt}/{max_attempts}")
                print(f"{'='*60}")
                
                # Save the script to disk
                script_path = os.path.join(self.scripts_dir, f"{safe_name}_attempt_{attempt}.py")
                with open(script_path, "w") as f:
                    f.write(script_code)
                print(f"[SCRIPT] Saved: {script_path}")
                
                # Hot-reload the script module
                script_module = load_script_from_path(script_path)
                print(f"[SCRIPT] Loaded module: {script_module.__name__}")
                
                # Run the fight and record it
                print(f"\n[FIGHT] Starting fight attempt...")
                fight_result = self._run_fight_attempt(script_module, enemy_keyword)
                
                fight_video_path = fight_result.get("video_path")
                fight_duration = fight_result.get("duration", 0)
                print(f"[FIGHT] Fight ended after {fight_duration:.1f}s")
                
                # Record attempt in history
                attempt_record = {
                    "attempt": attempt,
                    "script_path": script_path,
                    "video_path": fight_video_path,
                    "duration": fight_duration,
                    "analysis": None,
                    "won": False,
                }
                
                if fight_video_path is None:
                    print(f"[FIGHT] No video recorded (fight may not have started)")
                    attempt_record["analysis"] = "No fight video — boss may not have appeared."
                    history.append(attempt_record)
                    continue
                
                # --- Upload fight video and get analysis + improved script ---
                print(f"\n[GEMINI] Uploading fight recording ({fight_duration:.1f}s)...")
                fight_file = self._upload_video(fight_video_path)
                
                print(f"[GEMINI] Requesting analysis and improved script...")
                response = chat.send_message([
                    types.Part(
                        file_data=types.FileData(file_uri=fight_file.uri),
                        video_metadata=types.VideoMetadata(fps=20)
                    ),
                    "I ran the last script you provided and attached the fight recording.\n\n"
                    "1. Did we WIN (enemy health bar depleted / enemy died) or LOSE (player died)?\n"
                    "   Start your response with exactly 'RESULT: WIN' or 'RESULT: LOSE'.\n\n"
                    "2. Analyze what went wrong (or right) and explain your reasoning.\n\n"
                    "3. Write an improved combat script incorporating your analysis."
                ])
                
                response_text = response.text
                print(f"[GEMINI] Response received ({len(response_text)} chars)")
                
                # Check win/loss
                won = "RESULT: WIN" in response_text.upper()
                attempt_record["won"] = won
                attempt_record["analysis"] = response_text[:500]  # Truncate for storage
                history.append(attempt_record)
                
                if won:
                    print(f"\n{'='*60}")
                    print(f"VICTORY on attempt {attempt}!")
                    print(f"{'='*60}")
                    return {
                        "status": "victory",
                        "attempts": attempt,
                        "winning_script": script_code,
                        "winning_script_path": script_path,
                        "history": history,
                    }
                
                # Parse improved script for next attempt
                new_script = self._parse_script(response_text)
                if new_script is None:
                    print(f"[GEMINI] Could not parse improved script, reusing previous script")
                else:
                    script_code = new_script
                    print(f"[GEMINI] Improved script received ({len(script_code)} chars)")
                
                # Brief log of Gemini's analysis
                analysis_preview = response_text[:300].replace('\n', ' ')
                print(f"[ANALYSIS] {analysis_preview}...")
            
            # Max attempts exhausted
            print(f"\n{'='*60}")
            print(f"Max attempts ({max_attempts}) reached without victory.")
            print(f"{'='*60}")
            return {
                "status": "max_attempts",
                "attempts": max_attempts,
                "history": history,
            }
        
        finally:
            # Always clean up tracker and release keys
            actions.release_all()
            if tracker:
                tracker.stop()
                print("[TRACKER] Stopped")
    
    # =========================================================
    # FIGHT EXECUTION
    # =========================================================
    
    def _run_fight_attempt(self, script_module, enemy_keyword: str) -> dict:
        """
        Execute one fight attempt: wait for boss, run script, record, detect end.
        
        Uses tracker-based detection:
        - Wait until the boss entity appears in game_state
        - Start recording + script execution
        - When boss disappears for boss_gone_threshold seconds, fight is over
        - Hard timeout as a safety net
        
        Args:
            script_module: Loaded script with run(game_state, actions)
            enemy_keyword: Lowercase keyword to match entity names (e.g. "empress")
        
        Returns:
            Dict with video_path (str or None) and duration (float).
        """
        # Step 1: Wait for the boss to appear
        print(f"  Waiting for boss ('{enemy_keyword}') to appear in game state...")
        boss_appeared = self._wait_for_boss(enemy_keyword, timeout=120)
        
        if not boss_appeared:
            print(f"  Boss did not appear within 120s. Skipping this attempt.")
            return {"video_path": None, "duration": 0}
        
        print(f"  Boss detected! Starting fight...")
        
        # Step 2: Start recording + script execution
        recorder = ScreenRecorder(fps=self.recording_fps)
        recorder.start()
        
        stop_event = threading.Event()
        
        # Run the script in a background thread so we can monitor boss state
        script_thread = threading.Thread(
            target=run_script_timed,
            args=(script_module, stop_event),
            kwargs={"fps": self.fight_fps, "verbose": True},
            daemon=True,
        )
        script_thread.start()
        
        fight_start = time.time()
        
        # Step 3: Monitor for fight end (boss gone for N seconds)
        boss_last_seen = time.time()
        
        while not stop_event.is_set():
            time.sleep(0.5)  # Poll every 500ms
            
            elapsed = time.time() - fight_start
            
            # Check if boss is still visible
            entities = game_state.get_found_entities()
            boss_visible = any(enemy_keyword in name.lower() for name in entities.keys())
            
            if boss_visible:
                boss_last_seen = time.time()
            
            # Boss gone for threshold seconds → fight over
            boss_gone_for = time.time() - boss_last_seen
            if boss_gone_for >= self.boss_gone_threshold:
                print(f"  Boss not seen for {self.boss_gone_threshold}s — fight over.")
                stop_event.set()
                break
            
            # Hard timeout
            if elapsed >= self.fight_timeout:
                print(f"  Hard timeout ({self.fight_timeout}s) reached — stopping fight.")
                stop_event.set()
                break
        
        # Step 4: Stop everything and save recording
        script_thread.join(timeout=3.0)
        video_bytes = recorder.stop()
        fight_duration = time.time() - fight_start
        
        # Save fight video to disk (Gemini Files API needs a file path)
        video_path = None
        if video_bytes:
            safe_keyword = re.sub(r'[^\w]', '_', enemy_keyword)
            video_path = os.path.join(
                self.videos_dir,
                f"{safe_keyword}_attempt_{int(time.time())}.mp4"
            )
            with open(video_path, "wb") as f:
                f.write(video_bytes)
            print(f"  Fight video saved: {video_path} ({len(video_bytes) // 1024}KB)")
        
        return {"video_path": video_path, "duration": fight_duration}
    
    def _wait_for_boss(self, enemy_keyword: str, timeout: float = 120) -> bool:
        """Poll game_state until the boss entity appears, or timeout."""
        start = time.time()
        while time.time() - start < timeout:
            entities = game_state.get_found_entities()
            if any(enemy_keyword in name.lower() for name in entities.keys()):
                return True
            time.sleep(0.5)
        return False
    
    # =========================================================
    # GEMINI HELPERS
    # =========================================================
    
    def _upload_video(self, video_path: str):
        """Upload a video to the Gemini Files API and wait for processing."""
        myfile = self.client.files.upload(file=video_path)
        
        while myfile.state.name == "PROCESSING":
            time.sleep(5)
            myfile = self.client.files.get(name=myfile.name)
        
        if myfile.state.name == "FAILED":
            raise RuntimeError(f"Video upload failed: {myfile.state.name}")
        
        return myfile
    
    def _parse_script(self, response_text: str) -> str | None:
        """Extract a Python script from Gemini's markdown response.
        
        Looks for a ```python code block, validates it has a run() function.
        Returns the code string, or None if parsing fails.
        """
        # Try to find a python code block
        match = re.search(r'```python\s*\n(.*?)```', response_text, re.DOTALL)
        if not match:
            # Fallback: try any code block
            match = re.search(r'```\s*\n(.*?)```', response_text, re.DOTALL)
        
        if not match:
            print(f"  [PARSE] No code block found in response")
            return None
        
        code = match.group(1).strip()
        
        # Validate it has a run function
        if "def run(" not in code:
            print(f"  [PARSE] Code block found but no 'def run(' function")
            return None
        
        return code
    
    def _build_system_prompt(self, enemy_name: str, enemy_context: str = "") -> str:
        """Build the system prompt for combat script generation, parameterized by enemy."""
        
        context_section = ""
        if enemy_context:
            context_section = f"""
## Your kit
{enemy_context}
"""
        
        return f"""
You are a game AI script writer. Your task is to write a Python combat script that defeats the {enemy_name} based on video footage you've analyzed.

## GAME STATE

You have access to a `game_state` object with real-time enemy positions:
- `game_state.get_found_entities()` returns a dict of visible enemies: {{"enemy_name": {{"x": 800, "y": 400, "found": True}}}}
- The PLAYER is ALWAYS at the CENTER of the screen (x=1280, y=720 on a 2560x1440 display)
- Enemy coordinates are in screen pixels, updated every frame (~30 FPS)

## HOW ACTIONS WORK (IMPORTANT)

All actions are **non-blocking intent declarations**. Your `run()` function is called every frame.
You declare what you want to happen THIS frame by calling action methods. After `run()` returns,
the engine applies everything in a single pass (~5-15ms total). This means:

- You can call AS MANY actions as you want per frame with NO performance penalty
- Actions do NOT have duration parameters — they apply for exactly one frame
- To keep moving left, call `actions.move_left()` every frame
- To stop moving, simply stop calling the method — the key is auto-released next frame
- Mouse attack is held while you keep calling `attack_at()` — released when you stop

## AVAILABLE ACTIONS

Movement (call each frame you want the key held):
- actions.move_left()  — Hold left (A key) this frame
- actions.move_right() — Hold right (D key) this frame
- actions.fly_up()     — Hold fly/jump (Space key) this frame
- actions.move_down()  — Hold down (S key) this frame

Dashes (one-shot, queued):
- actions.dash_left()  — Dash left (double-tap A). One dash per frame max
- actions.dash_right() — Dash right (double-tap D). One dash per frame max

Combat:
- actions.attack_at(x, y) — Aim mouse at (x, y) and hold attack this frame
{context_section}
## YOUR TASK

Based on the enemy video footage you've seen, write a Python script that defeats the enemy, avoiding being hit while also attacking it.

## SCRIPT FORMAT

Your script must have this structure:

```python
\"\"\"
Combat script: {enemy_name}
Strategy: [Brief description of your approach]
\"\"\"

# Configuration
PLAYER_X = 1280  # Player always at screen center
PLAYER_Y = 720

def run(game_state, actions):
    '''Called every frame. Declare all actions for this frame.'''
    enemies = game_state.get_found_entities()
    # Your combat logic here
```

## Here's an example script:

```python
SCREEN_CENTER_X = 1280

def run(game_state, actions):
    entities = game_state.get_found_entities()
    if not entities:
        return
    for name, entity in entities.items():
        x, y = entity["x"], entity["y"]
        if x < SCREEN_CENTER_X:
            actions.move_right()
        else:
            actions.move_left()
        actions.attack_at(x, y)
        break
```

### Keep in mind 
- All actions are non-blocking. Call multiple actions per frame freely (e.g. move + attack + fly simultaneously)
- Enemy will not always be on your screen when attacking you, so continue to attack their last known location
- Enemy's name will always be lower case
- There is an infinite horizontal platform
- Constantly holding the movement key in the opposite direction of the enemy is highly advised
- When the enemy gets too close, dashing into them will make it so you dont take any damage
"""


# =========================================================
# CLI ENTRY POINT
# =========================================================

def main():
    parser = argparse.ArgumentParser(
        description="Combat Learner - AI that teaches itself to fight game bosses"
    )
    parser.add_argument(
        "--enemy", "-e", required=True,
        help="Name of the enemy (e.g. 'Empress of Light')"
    )
    parser.add_argument(
        "--video", "-v", required=True,
        help="Path to a video showing the enemy in action"
    )
    parser.add_argument(
        "--max-attempts", "-n", type=int, default=10,
        help="Maximum number of fight attempts (default: 10)"
    )
    parser.add_argument(
        "--context", "-c", default="",
        help="Extra context about player kit/weapons (e.g. 'Homing gun, very fast movement')"
    )
    parser.add_argument(
        "--fight-timeout", type=int, default=180,
        help="Hard timeout per fight attempt in seconds (default: 180)"
    )
    parser.add_argument(
        "--boss-gone-threshold", type=int, default=15,
        help="Seconds boss must be gone to consider fight over (default: 15)"
    )
    
    args = parser.parse_args()
    
    learner = CombatLearner()
    learner.fight_timeout = args.fight_timeout
    learner.boss_gone_threshold = args.boss_gone_threshold
    
    result = learner.learn_to_fight(
        enemy_name=args.enemy,
        enemy_video_path=args.video,
        max_attempts=args.max_attempts,
        enemy_context=args.context,
    )
    
    # Print final summary
    print(f"\n{'='*60}")
    print(f"FINAL RESULT: {result['status'].upper()}")
    print(f"Attempts: {result.get('attempts', 0)}")
    if result["status"] == "victory":
        print(f"Winning script: {result.get('winning_script_path', 'N/A')}")
    print(f"{'='*60}")
    
    # Print per-attempt summary
    for h in result.get("history", []):
        status = "WIN" if h.get("won") else "LOSE"
        print(f"  Attempt {h['attempt']}: {status} ({h['duration']:.1f}s)")


if __name__ == "__main__":
    main()

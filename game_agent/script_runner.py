"""
Script runner - loads and runs behavior scripts in a loop.

Provides both a CLI interface and a programmatic API for the combat learner.

Usage (CLI):
    python script_runner.py --script dodge_enemy
    python script_runner.py --script dodge_enemy --confidence 0.9
"""

import argparse
import importlib.util
import threading
import time
import sys
import os

from game_state import game_state
from actions import actions
from tracker_service import create_tracker_from_extraction_dir


def load_script(script_name: str):
    """Load a behavior script from the test_scripts directory by name."""
    script_dir = os.path.join(os.path.dirname(__file__), "test_scripts")
    script_path = os.path.join(script_dir, f"{script_name}.py")
    
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    
    return load_script_from_path(script_path)


def load_script_from_path(script_path: str):
    """Load a behavior script from an arbitrary file path.
    
    Used by combat_learner to hot-reload generated scripts.
    
    Args:
        script_path: Absolute or relative path to a .py file with a run() function.
    
    Returns:
        The loaded module with a run(game_state, actions) function.
    """
    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Script not found: {script_path}")
    
    # Use a unique module name based on path + timestamp to avoid caching
    module_name = f"script_{os.path.basename(script_path).replace('.py', '')}_{int(time.time())}"
    
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    
    if not hasattr(module, "run"):
        raise AttributeError(f"Script {script_path} must have a 'run(game_state, actions)' function")
    
    return module


def run_script_loop(script_module, fps: int = 60, verbose: bool = True):
    """Run the script in an infinite loop until Ctrl+C (CLI usage)."""
    frame_time = 1.0 / fps
    frame_count = 0
    start_time = time.time()
    
    print(f"\n{'='*50}")
    print(f"Running script: {script_module.__name__}")
    print(f"FPS target: {fps}")
    print(f"Press Ctrl+C to stop")
    print(f"{'='*50}\n")
    
    try:
        while True:
            loop_start = time.time()
            
            # Run the script (sets action intents), then flush inputs
            try:
                script_module.run(game_state, actions)
            except Exception as e:
                print(f"[ERROR] Script error: {e}")
            
            # Apply all intents as actual game inputs in one pass
            actions.flush()
            
            frame_count += 1
            
            # Log periodically
            if verbose and frame_count % fps == 0:
                elapsed = time.time() - start_time
                actual_fps = frame_count / elapsed
                entities = game_state.get_found_entities()
                entity_str = ", ".join([f"{k}@({v['x']},{v['y']})" for k, v in entities.items()])
                print(f"[{elapsed:.1f}s] FPS: {actual_fps:.1f} | Entities: {entity_str or 'none'}")
            
            # Maintain FPS
            elapsed = time.time() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    except KeyboardInterrupt:
        print("\n\nStopped by user")


def run_script_timed(script_module, stop_event: threading.Event, fps: int = 30, verbose: bool = True) -> dict:
    """Run a script loop until stop_event is set. Programmatic API for combat_learner.
    
    Unlike run_script_loop, this function:
    - Exits cleanly when stop_event is set (no Ctrl+C needed)
    - Returns stats about the run
    - Releases all held keys on exit
    
    Args:
        script_module: Loaded module with a run(game_state, actions) function.
        stop_event: threading.Event — set this from another thread to stop the loop.
        fps: Target frames per second.
        verbose: Whether to print periodic status logs.
    
    Returns:
        Dict with {frame_count, elapsed, actual_fps}.
    """
    frame_time = 1.0 / fps
    frame_count = 0
    start_time = time.time()
    
    try:
        while not stop_event.is_set():
            loop_start = time.time()
            
            # Run the script (sets action intents), then flush inputs
            try:
                script_module.run(game_state, actions)
            except Exception as e:
                print(f"[ERROR] Script error: {e}")
            
            actions.flush()
            frame_count += 1
            
            # Log periodically
            if verbose and frame_count % fps == 0:
                elapsed = time.time() - start_time
                actual_fps = frame_count / elapsed if elapsed > 0 else 0
                entities = game_state.get_found_entities()
                entity_str = ", ".join([f"{k}@({v['x']},{v['y']})" for k, v in entities.items()])
                print(f"  [{elapsed:.1f}s] FPS: {actual_fps:.1f} | Entities: {entity_str or 'none'}")
            
            # Maintain FPS
            elapsed = time.time() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    finally:
        # Always release keys when the loop ends
        actions.release_all()
    
    elapsed = time.time() - start_time
    return {
        "frame_count": frame_count,
        "elapsed": elapsed,
        "actual_fps": frame_count / elapsed if elapsed > 0 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="Run a behavior script with entity tracking")
    parser.add_argument("--script", "-s", required=True, help="Name of script in test_scripts/")
    parser.add_argument("--confidence", "-c", type=float, default=0.85, help="Tracking confidence")
    parser.add_argument("--fps", type=int, default=60, help="Script execution FPS")
    parser.add_argument("--quiet", "-q", action="store_true", help="Reduce logging")
    
    parser.add_argument("--accurate", action="store_true", help="Disable optimizations for higher accuracy (slower)")
    parser.add_argument("--downscale-factor", type=float, default=0.5, help="Downscale factor for faster matching (0.5 = 2x faster)")
    
    args = parser.parse_args()
    
    # Load the script
    print(f"Loading script: {args.script}")
    script_module = load_script(args.script)
    print(f"Script loaded: {script_module.__name__}")
    
    # Determine settings
    downscale = 1.0 if args.accurate else args.downscale_factor
    skip_full = False if args.accurate else True
    
    # Start tracker service
    print(f"\nStarting tracker service (Accurate: {args.accurate}, Downscale: {downscale})...")
    tracker = create_tracker_from_extraction_dir(
        confidence=args.confidence,
        downscale_factor=downscale,
        skip_full_scan=skip_full
    )
    tracker.start()
    
    # Wait for tracker to get first positions
    time.sleep(0.5)
    
    try:
        # Run the script loop
        run_script_loop(script_module, fps=args.fps, verbose=not args.quiet)
    finally:
        # Release all held keys/mouse before shutting down
        actions.release_all()
        tracker.stop()
        print("Tracker stopped")


if __name__ == "__main__":
    main()

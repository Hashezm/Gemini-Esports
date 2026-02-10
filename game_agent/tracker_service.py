"""
Tracker service that runs simple_match in a background thread
and updates game_state with entity positions.
"""

import threading
import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '2dgametest'))

from game_state import game_state


class TrackerService:
    """
    Background service that tracks entities and updates game_state.
    """
    
    def __init__(self, template_paths: list, confidence: float = 0.85, 
                 search_margin: int = 150, fps: int = 60,
                 downscale_factor: float = 0.5, skip_full_scan: bool = True):
        """
        Args:
            template_paths: List of (name, path) tuples or just paths
        """
        self.running = False
        self.thread = None
        self.fps = fps
        self.frame_count = 0
        self.confidence = confidence
        self.search_margin = search_margin
        self.downscale_factor = downscale_factor
        self.skip_full_scan = skip_full_scan
        
        # Parse template paths
        self.templates = []
        for item in template_paths:
            if isinstance(item, tuple):
                name, path = item
            else:
                # Extract name from path
                name = os.path.basename(os.path.dirname(item))
                if name == "extraction_stuff":
                    name = os.path.splitext(os.path.basename(item))[0]
                path = item
            self.templates.append({"name": name, "path": path})
        
        print(f"[TrackerService] Initialized with {len(self.templates)} templates")
        for t in self.templates:
            print(f"  - {t['name']}: {t['path']}")
    
    def _tracking_loop(self):
        """Main tracking loop (runs in background thread)."""
        # IMPORTANT: Create tracker HERE in the background thread
        # mss uses thread-local storage and must be created in the same thread that uses it
        from simple_match import MultiTemplateTrackerCV
        
        paths = [t["path"] for t in self.templates]
        tracker = MultiTemplateTrackerCV(
            paths,
            confidence=self.confidence,
            search_margin=self.search_margin,
            max_workers=len(paths),
            downscale_factor=self.downscale_factor,  # Enable pyramid optimization
            skip_full_scan=self.skip_full_scan       # Skip expensive full scan on miss
        )
        
        frame_time = 1.0 / self.fps
        
        try:
            while self.running:
                loop_start = time.time()
                
                # Get positions for all templates
                results = tracker.find_all()
                
                # Update game state
                for i, result in enumerate(results):
                    name = self.templates[i]["name"]
                    game_state.update_entity(
                        name=name,
                        x=result.x,
                        y=result.y,
                        found=result.found,
                        method=result.method,
                        width=result.w,
                        height=result.h
                    )
                
                self.frame_count += 1
                
                # Maintain target FPS
                elapsed = time.time() - loop_start
                sleep_time = frame_time - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            tracker.shutdown()
    
    def start(self):
        """Start the tracking service."""
        if self.running:
            print("[TrackerService] Already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self.thread.start()
        print("[TrackerService] Started")
    
    def stop(self):
        """Stop the tracking service."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        print("[TrackerService] Stopped")
    
    def get_stats(self):
        """Get tracking statistics."""
        return {
            "frames": self.frame_count,
            "templates": len(self.templates),
            "running": self.running
        }


def create_tracker_from_extraction_dir(extraction_dir: str = None, confidence: float = 0.85,
                                       downscale_factor: float = 0.5, skip_full_scan: bool = True):
    """
    Create a TrackerService from all reference_crop.png files in extraction directory.
    """
    import glob
    
    if extraction_dir is None:
        extraction_dir = os.path.join(os.path.dirname(__file__), "extraction_stuff")
    
    # Find all reference crops
    pattern = os.path.join(extraction_dir, "*", "reference_crop.png")
    paths = glob.glob(pattern)
    
    if not paths:
        raise FileNotFoundError(f"No reference_crop.png files found in {extraction_dir}")
    
    # Create (name, path) tuples
    template_paths = []
    for path in paths:
        name = os.path.basename(os.path.dirname(path))
        template_paths.append((name, path))
    
    return TrackerService(template_paths, confidence=confidence, 
                          downscale_factor=downscale_factor, skip_full_scan=skip_full_scan)


"""
Maximum speed template matching using PyAutoGUI with all optimizations:
1. ROI/Region search (heuristic search around last position)
2. Pre-loaded template image
3. mss for fast screenshots
4. grayscale matching
5. DOWNSCALING - shrink images before matching for massive speedup
6. Optional: disable preview for max speed
"""

import pyautogui
import cv2 as cv
import numpy as np
import mss
import time
import os
from PIL import Image


class FastSpriteTracker:
    """
    Maximum speed sprite tracking using PyAutoGUI with downscaling.
    """
    
    def __init__(self, template_path: str, confidence: float = 0.7, 
                 search_margin: int = 150, grayscale: bool = True,
                 scale: float = 0.5):
        """
        Args:
            template_path: Path to template image
            confidence: Match confidence (0.0-1.0)
            search_margin: Pixels around last position to search
            grayscale: Use grayscale matching (faster)
            scale: Downscale factor (0.5 = half size, much faster)
        """
        # Pre-load template image
        self.template_original = Image.open(template_path)
        self.template_path = template_path
        self.original_w, self.original_h = self.template_original.size
        
        # Downscale template for faster matching (Optimization #5)
        self.scale = scale
        new_w = int(self.original_w * scale)
        new_h = int(self.original_h * scale)
        self.template = self.template_original.resize((new_w, new_h), Image.BILINEAR)
        self.w, self.h = new_w, new_h
        
        self.confidence = confidence
        self.search_margin = int(search_margin * scale)  # Scale margin too
        self.grayscale = grayscale
        
        # Last known position for heuristic search (in SCALED coords)
        self.last_pos = None
        
        # Screen capture with mss
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        self.screen_w = self.monitor['width']
        self.screen_h = self.monitor['height']
        self.scaled_screen_w = int(self.screen_w * scale)
        self.scaled_screen_h = int(self.screen_h * scale)
        
        print(f"[FastSpriteTracker] Template: {template_path}")
        print(f"[FastSpriteTracker] Original size: {self.original_w}x{self.original_h}")
        print(f"[FastSpriteTracker] Scaled size: {self.w}x{self.h} (scale={scale})")
        print(f"[FastSpriteTracker] Confidence: {confidence} | Grayscale: {grayscale}")
    
    def capture_and_scale(self):
        """Capture full screen and downscale for faster matching."""
        sct_img = self.sct.grab(self.monitor)
        img = Image.frombytes('RGB', (sct_img.width, sct_img.height), sct_img.rgb)
        # Downscale for speed
        return img.resize((self.scaled_screen_w, self.scaled_screen_h), Image.BILINEAR)
    
    def capture_region_and_scale(self, x, y, w, h):
        """Capture specific region and downscale."""
        # Convert scaled coords back to screen coords
        screen_x = int(x / self.scale)
        screen_y = int(y / self.scale)
        screen_w = int(w / self.scale)
        screen_h = int(h / self.scale)
        
        region = {
            'left': max(0, screen_x),
            'top': max(0, screen_y),
            'width': min(screen_w, self.screen_w - screen_x),
            'height': min(screen_h, self.screen_h - screen_y)
        }
        sct_img = self.sct.grab(region)
        img = Image.frombytes('RGB', (sct_img.width, sct_img.height), sct_img.rgb)
        
        # Downscale
        scaled_w = int(region['width'] * self.scale)
        scaled_h = int(region['height'] * self.scale)
        return img.resize((scaled_w, scaled_h), Image.BILINEAR), region
    
    def find_sprite(self):
        """
        Find sprite using heuristic search with downscaling.
        
        Returns:
            Tuple of (found, x, y, w, h, method) in SCREEN coords
        """
        
        # Heuristic Search in ROI
        if self.last_pos is not None:
            lx, ly = self.last_pos  # Scaled coords
            
            # Define search region in scaled coords
            roi_x = max(0, lx - self.search_margin)
            roi_y = max(0, ly - self.search_margin)
            roi_w = min(self.search_margin * 2 + self.w, self.scaled_screen_w - roi_x)
            roi_h = min(self.search_margin * 2 + self.h, self.scaled_screen_h - roi_y)
            
            # Capture and scale the ROI
            roi_screenshot, screen_region = self.capture_region_and_scale(roi_x, roi_y, roi_w, roi_h)
            
            try:
                location = pyautogui.locate(
                    self.template, 
                    roi_screenshot,
                    confidence=self.confidence,
                    grayscale=self.grayscale
                )
            except Exception:
                location = None
            
            if location is not None:
                # Convert back to screen coords
                # ROI offset in screen coords
                screen_x = screen_region['left'] + int(location.left / self.scale)
                screen_y = screen_region['top'] + int(location.top / self.scale)
                
                # Update last_pos in scaled coords
                self.last_pos = (int(screen_x * self.scale), int(screen_y * self.scale))
                
                return True, screen_x, screen_y, self.original_w, self.original_h, "Heuristic"
        
        # Full screen search (fallback)
        screenshot = self.capture_and_scale()
        
        try:
            location = pyautogui.locate(
                self.template,
                screenshot,
                confidence=self.confidence,
                grayscale=self.grayscale
            )
        except Exception:
            location = None
        
        if location is not None:
            # Convert scaled coords to screen coords
            screen_x = int(location.left / self.scale)
            screen_y = int(location.top / self.scale)
            
            # Store in scaled coords
            self.last_pos = (location.left, location.top)
            
            return True, screen_x, screen_y, self.original_w, self.original_h, "Full Scan"
        
        # Not found
        self.last_pos = None
        return False, 0, 0, 0, 0, "Not Found"
    
    def get_frame_for_preview(self):
        """Get current screen as numpy array for cv2 preview."""
        sct_img = self.sct.grab(self.monitor)
        frame = np.array(sct_img)
        return cv.cvtColor(frame, cv.COLOR_BGRA2BGR)


def run_tracking_loop(template_path: str, confidence: float = 0.7, 
                      search_margin: int = 150, fps: int = 60,
                      scale: float = 0.5, show_preview: bool = False):
    """
    Run the optimized tracking loop.
    
    Args:
        scale: Downscale factor (0.5 = half resolution, faster)
        show_preview: Set False for maximum speed (no display overhead)
    """
    tracker = FastSpriteTracker(
        template_path, 
        confidence=confidence,
        search_margin=search_margin,
        grayscale=True,
        scale=scale
    )
    
    frame_time = 1.0 / fps
    frame_count = 0
    heuristic_count = 0
    full_scan_count = 0
    start_time = time.time()
    
    print(f"Preview: {'ON' if show_preview else 'OFF (max speed)'}")
    print("Press 'q' to quit" if show_preview else "Press Ctrl+C to quit")
    print("-" * 50)
    
    try:
        while True:
            loop_start = time.time()
            
            # Find sprite
            found, x, y, w, h, method = tracker.find_sprite()
            
            # Stats
            frame_count += 1
            if method == "Heuristic":
                heuristic_count += 1
            elif method == "Full Scan":
                full_scan_count += 1
                
            elapsed = time.time() - start_time
            actual_fps = frame_count / elapsed if elapsed > 0 else 0
            
            # Log
            if found:
                print(f"Frame {frame_count} (FPS: {actual_fps:.1f}): FOUND at ({x}, {y}) | {method}")
            else:
                if frame_count % max(1, int(actual_fps)) == 0:
                    print(f"Frame {frame_count} (FPS: {actual_fps:.1f}): Not found")
            
            # Preview (optional - disable for max speed)
            if show_preview:
                frame = tracker.get_frame_for_preview()
                
                if found:
                    cv.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    cv.putText(frame, f"{method}", (x, y - 10), 
                              cv.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                
                cv.putText(frame, f"FPS: {int(actual_fps)}", (10, 30), 
                          cv.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                
                status = "TRACKING" if found else "SEARCHING..."
                color = (0, 255, 0) if found else (0, 0, 255)
                cv.putText(frame, status, (10, 60), 
                          cv.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                
                preview = cv.resize(frame, (1280, 720))
                cv.imshow("Fast Sprite Tracker", preview)
                
                if cv.waitKey(1) & 0xFF == ord('q'):
                    break
            
            # Maintain FPS (relax timing for speed)
            # loop_elapsed = time.time() - loop_start
            # sleep_time = frame_time - loop_elapsed
            # if sleep_time > 0:
            #     time.sleep(sleep_time)
            
    except KeyboardInterrupt:
        print("\nInterrupted")
    finally:
        if show_preview:
            cv.destroyAllWindows()
        
        total_time = time.time() - start_time
        print(f"\n{'='*50}")
        print(f"Performance Summary")
        print(f"{'='*50}")
        print(f"Total frames: {frame_count}")
        print(f"Average FPS: {frame_count / total_time:.1f}")
        print(f"Heuristic: {heuristic_count} ({100*heuristic_count/max(1,frame_count):.1f}%)")
        print(f"Full scans: {full_scan_count} ({100*full_scan_count/max(1,frame_count):.1f}%)")


if __name__ == "__main__":
    import sys
    
    # Default template path: relative to this file's location
    default_template = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "game_agent", "extraction_stuff", "empress_of_light", "reference_crop.png")
    template = sys.argv[1] if len(sys.argv) > 1 else default_template
    confidence = float(sys.argv[2]) if len(sys.argv) > 2 else 0.7
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5  # Try 0.25 for even more speed
    
    # Set show_preview=False for maximum speed
    run_tracking_loop(template, confidence=confidence, search_margin=150, 
                      fps=60, scale=scale, show_preview=False)

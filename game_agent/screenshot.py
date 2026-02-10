"""
Screenshot Capture Utility
Simple wrapper for capturing screenshots as bytes for Gemini input.
Uses mss for fast capture.
"""

import mss
import io
from PIL import Image


def capture_screenshot(monitor: int = 1, max_size: int = 1280, quality: int = 80) -> bytes:
    """
    Capture a screenshot and return it as JPEG bytes (smaller for API calls).
    
    Args:
        monitor: Monitor number to capture (1 = primary)
        max_size: Max dimension (width or height). Resizes if larger. Set to None to skip.
        quality: JPEG quality (1-100). Lower = smaller file.
    
    Returns:
        JPEG image bytes ready to send to Gemini.
    """
    with mss.mss() as sct:
        screenshot = sct.grab(sct.monitors[monitor])
        
        # Convert to PIL Image
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        # Resize if too large
        if max_size and (img.width > max_size or img.height > max_size):
            ratio = min(max_size / img.width, max_size / img.height)
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.LANCZOS)
        
        # Encode to JPEG for smaller size
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()


def capture_screenshot_region(left: int, top: int, width: int, height: int) -> bytes:
    """
    Capture a specific region of the screen.
    
    Args:
        left: X coordinate of top-left corner
        top: Y coordinate of top-left corner  
        width: Width of region
        height: Height of region
    
    Returns:
        PNG image bytes of the region.
    """
    with mss.mss() as sct:
        region = {"left": left, "top": top, "width": width, "height": height}
        screenshot = sct.grab(region)
        
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return buffer.getvalue()


# Quick test
if __name__ == "__main__":
    print("Testing screenshot capture...")
    
    # Full screen
    screenshot_bytes = capture_screenshot()
    print(f"Full screenshot size: {len(screenshot_bytes) / 1024:.1f} KB")
    
    # Save to verify
    with open("test_screenshot.png", "wb") as f:
        f.write(screenshot_bytes)
    print("Saved test_screenshot.png")
    
    # Region capture
    region_bytes = capture_screenshot_region(0, 0, 800, 600)
    print(f"Region screenshot size: {len(region_bytes) / 1024:.1f} KB")
    
    with open("test_region.png", "wb") as f:
        f.write(region_bytes)
    print("Saved test_region.png")

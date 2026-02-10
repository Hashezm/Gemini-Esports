"""
Screen Recorder Module
Captures screen video during tool execution for the game agent system.
Uses mss for fast screenshots and opencv for video encoding.
"""

import mss
import cv2
import numpy as np
import threading
import time
import tempfile
import os


class ScreenRecorder:
    """Records screen to video bytes for sending to Gemini."""
    
    def __init__(self, fps: int = 10, monitor: int = 1):
        """
        Initialize the screen recorder.
        
        Args:
            fps: Frames per second for recording (default 10, good for Gemini analysis)
            monitor: Monitor number to capture (1 = primary)
        """
        self.fps = fps
        self.monitor = monitor
        self.frames = []
        self.recording = False
        self._thread = None
        self._sct = None
    
    def start(self):
        """Start recording the screen in a background thread."""
        if self.recording:
            return
        
        self.frames = []
        self.recording = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
    
    def stop(self) -> bytes:
        """
        Stop recording and return the video as bytes.
        
        Returns:
            MP4 video bytes ready to send to Gemini.
        """
        self.recording = False
        if self._thread:
            self._thread.join(timeout=2.0)
        
        if not self.frames:
            return b""
        
        return self._encode_to_mp4()
    
    def _capture_loop(self):
        """Background thread that captures frames at the specified FPS."""
        frame_interval = 1.0 / self.fps
        
        with mss.mss() as sct:
            monitor = sct.monitors[self.monitor]
            
            while self.recording:
                start_time = time.perf_counter()
                
                # Capture frame
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                # Convert BGRA to BGR (OpenCV format)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                self.frames.append(frame)
                
                # Maintain FPS timing
                elapsed = time.perf_counter() - start_time
                sleep_time = frame_interval - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
    
    def _encode_to_mp4(self) -> bytes:
        """Encode captured frames to MP4 bytes."""
        if not self.frames:
            return b""
        
        # Get frame dimensions from first frame
        height, width = self.frames[0].shape[:2]
        
        # Create temp file for video
        temp_path = os.path.join(tempfile.gettempdir(), f"recording_{time.time()}.mp4")
        
        try:
            # Use mp4v codec for compatibility
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(temp_path, fourcc, self.fps, (width, height))
            
            for frame in self.frames:
                writer.write(frame)
            
            writer.release()
            
            # Read back as bytes
            with open(temp_path, 'rb') as f:
                video_bytes = f.read()
            
            return video_bytes
        
        finally:
            # Cleanup temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    def get_frame_count(self) -> int:
        """Return the number of frames captured so far."""
        return len(self.frames)


# Quick test
if __name__ == "__main__":
    print("Testing screen recorder...")
    recorder = ScreenRecorder(fps=10)
    
    print("Recording for 3 seconds...")
    recorder.start()
    time.sleep(3)
    video_bytes = recorder.stop()
    
    print(f"Captured {recorder.get_frame_count()} frames")
    print(f"Video size: {len(video_bytes) / 1024:.1f} KB")
    
    # Save test video to verify it works
    with open("test_recording.mp4", "wb") as f:
        f.write(video_bytes)
    print("Saved test_recording.mp4 - check if it plays correctly!")

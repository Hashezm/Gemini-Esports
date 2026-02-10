import asyncio
import base64
import cv2
import mss
import numpy as np
import os
import logging
from google import genai
from google.genai import types
# --- CONFIGURATION ---
API_KEY = os.environ.get("GOOGLE_API_KEY")

MODEL_ID = "gemini-2.5-flash-native-audio-preview-12-2025" 
SCREEN_WIDTH = 1024  # Resize to this width (balance between quality and speed)

client = genai.Client(api_key=API_KEY)

# logging.getLogger("google.genai").setLevel(logging.ERROR)

async def main():
    # 1. Configure the connection
    config = {
        "response_modalities": ["AUDIO"], 
        "speech_config": {
            "voice_config": {"prebuilt_voice_config": {"voice_name": "Puck"}}
        },
        "output_audio_transcription": {},
    }
    
    # 2. Connect to the WebSocket
    async with client.aio.live.connect(model=MODEL_ID, config=config) as session:
        print(f"--- Connected to {MODEL_ID} ---")
        print(f"--- Streaming Screen Width: {SCREEN_WIDTH}px ---")
        print("--- Say something to the AI to get a response! ---")

        # Background Task: Receive Audio/Text from Gemini
        async def receive_loop():
            buf = []
            async for r in session.receive():
                sc = getattr(r, "server_content", None)
                if not sc:
                    continue

                if getattr(sc, "output_transcription", None):
                    chunk = sc.output_transcription.text
                    buf.append(chunk)
                    print(chunk, end="", flush=True)

                if getattr(sc, "turn_complete", False):
                    print("\n--- turn complete ---")
                    # full utterance if you want it:
                    full = "".join(buf)
                    buf.clear()

                # if getattr(response, "output_transcription", None):
                #     print(f"\n[AI said]: {response.output_transcription.text}")

        # Background Task: Send Screen Images
        async def send_screen_loop():
            with mss.mss() as sct:
                # Select Monitor 1
                monitor = sct.monitors[1]
                
                while True:
                    # A. Capture
                    screen_shot = sct.grab(monitor)
                    
                    # B. Convert to Numpy Array (OpenCV format)
                    img = np.array(screen_shot)
                    
                    # C. Color Fix (MSS gives BGRA, we need BGR)
                    frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
                    
                    # D. Resize (Crucial for latency!)
                    # Sending 4k images will lag. Resize to ~1024px width.
                    h, w = frame.shape[:2]
                    scale = SCREEN_WIDTH / w
                    new_h = int(h * scale)
                    frame = cv2.resize(frame, (SCREEN_WIDTH, new_h))
                    
                    # E. Encode to JPEG
                    _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                    jpeg_bytes = buffer.tobytes()
                    
                    # F. Send to Gemini
                    await session.send_realtime_input(
                            video={"data": jpeg_bytes, "mime_type": "image/jpeg"}
                        )
                    
                    # Rate Limit: 2 FPS is usually plenty for "Desktop QA"
                    await asyncio.sleep(0.5)

        # Background Task: Keep the script alive and allow you to type prompts
        async def user_input_loop():
             while True:
                text = await asyncio.to_thread(input, "Type to ask about screen: ")
                await session.send_client_content(turns=[types.Content(role="user", parts=[types.Part(text=text)])],
                    turn_complete=True)

        # Run everything simultaneously
        await asyncio.gather(receive_loop(), send_screen_loop(), user_input_loop())

if __name__ == "__main__":
    # Windows Asyncio Fix
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
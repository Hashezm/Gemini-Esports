# Audio-only Live API test
# Tests bidirectional audio streaming with Gemini Live API

import asyncio
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv
import pyaudio
import numpy as np

load_dotenv()

MODEL_NAME = 'gemini-2.0-flash-live-preview-04-09'

# Audio input with text responses - tests transcription
CONFIG = {
    "response_modalities": ["TEXT"],
    "realtime_input_config": {
        "automatic_activity_detection": {
            "disabled": False  # Let Gemini detect when user is speaking
        }
    },
    "input_audio_transcription": {},
    "system_instruction": "You are a helpful assistant. Listen to the user and respond helpfully."
}

# Audio settings
FORMAT = pyaudio.paInt16
CHANNELS = 1
INPUT_SAMPLE_RATE = 16000  # Input: 16kHz as per docs
OUTPUT_SAMPLE_RATE = 24000  # Output: 24kHz as per docs
CHUNK_SIZE = 1024

# Queue for audio playback
audio_queue = asyncio.Queue()


async def send_audio(session):
    """Capture audio from microphone and send to Gemini."""
    pya = pyaudio.PyAudio()
    
    # List available input devices
    print("\n=== Available Audio Input Devices ===")
    for i in range(pya.get_device_count()):
        info = pya.get_device_info_by_index(i)
        if info['maxInputChannels'] > 0:
            print(f"  [{i}] {info['name']}")
    print("=====================================\n")
    
    # Open input stream (default device)
    audio_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=INPUT_SAMPLE_RATE,
        input=True,
        frames_per_buffer=CHUNK_SIZE,
    )
    
    print("[Audio Input] Started capturing from microphone...")
    
    try:
        while True:
            # Read audio chunk
            data = await asyncio.to_thread(
                audio_stream.read, CHUNK_SIZE, exception_on_overflow=False
            )
            
            # Send to Gemini with correct MIME type
            await session.send_realtime_input(
                audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
            )
    except asyncio.CancelledError:
        audio_stream.stop_stream()
        audio_stream.close()
        pya.terminate()
        print("[Audio Input] Stopped")


async def play_audio():
    """Play audio from the queue."""
    pya = pyaudio.PyAudio()
    
    # Open output stream at 24kHz (Gemini's output rate)
    output_stream = await asyncio.to_thread(
        pya.open,
        format=FORMAT,
        channels=CHANNELS,
        rate=OUTPUT_SAMPLE_RATE,
        output=True,
        frames_per_buffer=CHUNK_SIZE,
    )
    
    print("[Audio Output] Ready to play responses...")
    
    try:
        while True:
            # Get audio chunk from queue
            chunk = await audio_queue.get()
            
            if chunk is None:
                # Interruption signal - flush buffer
                print("[Audio Output] Flushing buffer due to interruption")
                continue
            
            # Play the chunk
            await asyncio.to_thread(output_stream.write, chunk.tobytes())
    except asyncio.CancelledError:
        output_stream.stop_stream()
        output_stream.close()
        pya.terminate()
        print("[Audio Output] Stopped")


async def receive_responses(session):
    """Receive text responses from Gemini and print them."""
    print("[Receiver] Listening for responses...")
    
    try:
        async for msg in session.receive():
            server_content = msg.server_content
            
            if server_content:
                # 1. Handle Input Transcription (what Gemini heard)
                if server_content.input_transcription:
                    print(f"[You said]: {server_content.input_transcription.text}")
                
                # 2. Handle Interruption
                if server_content.interrupted:
                    print("\n[Interrupted]")
                    continue
                
                # 3. Process model response
                if server_content.model_turn:
                    for part in server_content.model_turn.parts:
                        if part.text:
                            print(f"[Gemini]: {part.text}", end="", flush=True)
                
                # 4. Check if turn is complete
                if server_content.turn_complete:
                    print("\n[Turn Complete]")
                    
    except asyncio.CancelledError:
        print("[Receiver] Stopped")


async def text_input(session):
    """Allow text input alongside audio for testing."""
    while True:
        text = await asyncio.to_thread(input, "Type message (or 'q' to quit): ")
        if text.lower() == 'q':
            break
        if text:
            await session.send_realtime_input(text=text)


async def run():
    print("=== Audio-Only Live API Test ===")
    print("Speak into your microphone. Gemini will respond with audio.")
    print("Type 'q' to quit.\n")
    
    client = genai.Client(http_options=types.HttpOptions(api_version="v1beta1"))
    
    async with client.aio.live.connect(
        model=MODEL_NAME,
        config=CONFIG
    ) as session:
        print("[Connected] Session established\n")
        
        # Start tasks (no audio playback needed for text responses)
        send_task = asyncio.create_task(send_audio(session))
        receive_task = asyncio.create_task(receive_responses(session))
        
        # Wait for text input (quit signal)
        await text_input(session)
        
        # Cancel all tasks
        send_task.cancel()
        receive_task.cancel()
        
        # Wait for cleanup
        await asyncio.gather(send_task, receive_task, return_exceptions=True)
    
    print("\n[Disconnected] Session closed")


if __name__ == "__main__":
    asyncio.run(run())

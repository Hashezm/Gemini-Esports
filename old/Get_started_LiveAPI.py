# -*- coding: utf-8 -*-
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
## Setup

To install the dependencies for this script, run:

``` 
pip install google-genai opencv-python pyaudio pillow mss
```

Before running this script, ensure the `GOOGLE_API_KEY` environment
variable is set to the api-key you obtained from Google AI Studio.

Important: **Use headphones**. This script uses the system default audio
input and output, which often won't include echo cancellation. So to prevent
the model from interrupting itself it is important that you use headphones. 

## Run

To run the script:

```
python Get_started_LiveAPI.py
```

The script takes a video-mode flag `--mode`, this can be "camera", "screen", or "none".
The default is "camera". To share your screen run:

```
python Get_started_LiveAPI.py --mode screen
```
"""

import asyncio
import base64
import io
import os
import sys
import traceback

import cv2
import pyaudio
import PIL.Image
import mss

import argparse

from dotenv import load_dotenv
from google import genai

load_dotenv()

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup
# def list_audio_devices():
#     p = pyaudio.PyAudio()
#     for i in range(p.get_device_count()):
#         info = p.get_device_info_by_index(i)

#         print(f"Device {i}: {info['name']}")
#         print(f"  Input Channels : {info['maxInputChannels']}")
#         print(f"  Output Channels: {info['maxOutputChannels']}")
#         print(f"  Default Sample Rate (Hz): {int(info['defaultSampleRate'])}")
#         print(f"  Host API: {p.get_host_api_info_by_index(info['hostApi'])['name']}")
# # Run this at the start of your script
# list_audio_devices()
"""
Device 1: CABLE Output (VB-Audio Virtual  (Input: 16, Output: 0) THIS SHOULD BE OUR MICROPHONE
Device 5: CABLE In 16ch (VB-Audio Virtual (Input: 0, Output: 16) i set this up at OUTPUT on Google Chrome
"""
FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024

MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

DEFAULT_MODE = "screen"

client = genai.Client(http_options={"api_version": "v1beta"})

CONFIG = {"response_modalities": ["AUDIO"],
# "system_instruction": "You are a gaming assistant for a blind player, you need to guide the player in the game to clear a given stage in the game with the following description: A game where exploiting bugs is the only way to progress.So you found out you live in a simulation? At least you have this cool new job finding bugs in reality! Don't think like a player, think like a tester.",
"system_instruction": "Describe how many frames and how long of an audio you saw and heard in the last 10 seconds, then briefly describe the frames and audio"
,"realtime_input_config": {
        "automatic_activity_detection": {
            "disabled": True  
        }
    },
    "output_audio_transcription": {},
}

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode

        self.audio_in_queue = None
        self.out_queue = None

        self.session = None

        self.send_text_task = None
        self.receive_audio_task = None
        self.play_audio_task = None


    # def _get_frame(self, cap):
    #     # Read the frameq
    #     ret, frame = cap.read()
    #     # print("cap.read ret=", ret, "frame is None=", frame is None)

    #     # Check if the frame was read successfully
    #     if not ret:
    #         return None
    #     # Fix: Convert BGR to RGB color space
    #     # OpenCV captures in BGR but PIL expects RGB format
    #     # This prevents the blue tint in the video feed
    #     frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    #     img = PIL.Image.fromarray(frame_rgb)  # Now using RGB frame
    #     img.thumbnail([1024, 1024])

    #     image_io = io.BytesIO()
    #     img.save(image_io, format="jpeg")
    #     image_io.seek(0)

    #     mime_type = "image/jpeg"
    #     image_bytes = image_io.read()
    #     return {"mime_type": mime_type, "data": base64.b64encode(image_bytes).decode()}
    def _get_frame(self, cap):
        # Read the frame
        ret, frame = cap.read()
        if not ret:
            return None
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)
        img.thumbnail([1024, 1024])

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        mime_type = "image/jpeg"
        image_bytes = image_io.read()
        
        # CHANGED: Return raw bytes, do NOT base64 encode here
        return {"mime_type": mime_type, "data": image_bytes}

    async def get_frames(self):
        # This takes about a second, and will block the whole program
        # causing the audio pipeline to overflow if you don't to_thread it.
        cap = await asyncio.to_thread(
            cv2.VideoCapture, 0
        )  # 0 represents the default camera

        while True: 
            frame = await asyncio.to_thread(self._get_frame, cap)
            # print("captured frame", "ok" if frame else "none")
            if frame is None:
                break

            await asyncio.sleep(0.1)

            await self.out_queue.put(frame)

        # Release the VideoCapture object
        cap.release()

    def _get_screen(self):
        sct = mss.mss()
        monitor = sct.monitors[0]

        i = sct.grab(monitor)

        mime_type = "image/jpeg"
        image_bytes = mss.tools.to_png(i.rgb, i.size)
        img = PIL.Image.open(io.BytesIO(image_bytes))

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg")
        image_io.seek(0)

        image_bytes = image_io.read()
        
        return {"mime_type": mime_type, "data": image_bytes}

    async def get_screen(self):

        while True:
            frame = await asyncio.to_thread(self._get_screen)
            if frame is None:
                break

            await asyncio.sleep(0.1)

            await self.out_queue.put(frame)

    async def send_realtime(self):
        messages_sent = {"audio/pcm": 0, "image/jpeg": 0, "other": 0}
        while True:
            msg = await self.out_queue.get()
            mime_type = msg.get("mime_type", "unknown") if isinstance(msg, dict) else "text"
            
            if "audio" in mime_type:
                messages_sent["audio/pcm"] += 1
                await self.session.send_realtime_input(
                    audio={"data": msg["data"], "mime_type": msg["mime_type"]}
                )
            elif "image" in mime_type:
                # Send video using the specific helper method (note the 'video' argument)
                await self.session.send_realtime_input(
                    video={"data": msg["data"], "mime_type": msg["mime_type"]}
                )
            
            # Log every 50 messages
            total = sum(messages_sent.values())
            # if total % 50 == 0:
            #     print(f"[DEBUG] Sent to Gemini: {messages_sent} | Queue size: {self.out_queue.qsize()}")
                
            # CRITICAL: Do NOT call session.send(input=msg) here. 
            # That was causing the duplication and the protocol error.
            


    async def send_text(self):
        while True:
            text = await asyncio.to_thread(
                input,
                "message > ",
            )
            if text.lower() == "q":
                break
            
            await self.session.send(input=text or ".", end_of_turn=True)


    async def listen_audio(self):
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=29,
            frames_per_buffer=CHUNK_SIZE,
        )
   
        while True:
            data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)            
            await self.out_queue.put({"data": data, "mime_type": "audio/pcm"})


    async def receive_audio(self):
        "Background task to reads from the websocket and write pcm chunks to the output queue"
        while True:
            turn = self.session.receive()
            transcript = ""
            async for response in turn:
                # print(response)
                if data := response.data:
                    self.audio_in_queue.put_nowait(data)
                    continue
                if text := response.text:
                    print(text, end="")
                server_content = response.server_content
                
                if server_content and server_content.output_transcription:
                    transcript += server_content.output_transcription.text
                else:
                    print(f"Transcript: {transcript}")

            # If you interrupt the model, it sends a turn_complete.
            # For interruptions to work, we need to stop playback.
            # So empty out the audio queue because it may have loaded
            # much more audio than has played yet.
            while not self.audio_in_queue.empty():
                self.audio_in_queue.get_nowait()

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        while True:
            bytestream = await self.audio_in_queue.get()
            await asyncio.to_thread(stream.write, bytestream)

    async def run(self):
        try:
            async with (
                client.aio.live.connect(model=MODEL, config=CONFIG) as session,
                asyncio.TaskGroup() as tg,
            ):
                self.session = session

                self.audio_in_queue = asyncio.Queue()
                self.out_queue = asyncio.Queue(maxsize=5)

                send_text_task = tg.create_task(self.send_text())
                tg.create_task(self.send_realtime())
                tg.create_task(self.listen_audio())
                if self.video_mode == "camera":
                    tg.create_task(self.get_frames())
                elif self.video_mode == "screen":
                    tg.create_task(self.get_screen())

                tg.create_task(self.receive_audio())
                tg.create_task(self.play_audio())

                await send_text_task
                raise asyncio.CancelledError("User requested exit")

        except asyncio.CancelledError:
            pass
        except ExceptionGroup as EG:
            self.audio_stream.close()
            traceback.print_exception(EG)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioLoop(video_mode=args.mode)
    asyncio.run(main.run())


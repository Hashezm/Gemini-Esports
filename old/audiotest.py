# record_ai_input.py
# Records exactly what your AI loop "hears": the PyAudio INPUT device you pick
# Saves a 16kHz mono 16-bit PCM WAV.

import wave
import time
import pyaudio

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024

# Set this to the same one you use in listen_audio()
INPUT_DEVICE_INDEX = 29  # <-- change to your VB-CABLE "Output" device index
SECONDS = 10             # <-- recording length
OUT_WAV = "ai_hearing.wav"

def list_audio_devices():
    p = pyaudio.PyAudio()
    for i in range(p.get_device_count()):
        info = p.get_device_info_by_index(i)
        print(
            f"[{i}] {info['name']} | "
            f"in={info['maxInputChannels']} out={info['maxOutputChannels']} | "
            f"default_hz={int(info['defaultSampleRate'])}"
        )
    p.terminate()

def record():
    p = pyaudio.PyAudio()

    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        input_device_index=INPUT_DEVICE_INDEX,
        frames_per_buffer=CHUNK,
    )

    frames = []
    print(f"Recording {SECONDS}s from device {INPUT_DEVICE_INDEX} -> {OUT_WAV}")
    t_end = time.time() + SECONDS

    try:
        while time.time() < t_end:
            data = stream.read(CHUNK, exception_on_overflow=False)
            frames.append(data)
    finally:
        stream.stop_stream()
        stream.close()
        p.terminate()

    with wave.open(OUT_WAV, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(pyaudio.PyAudio().get_sample_size(FORMAT))
        wf.setframerate(RATE)
        wf.writeframes(b"".join(frames))

    print("Done.")

if __name__ == "__main__":
    # Uncomment to find the right INPUT_DEVICE_INDEX:
    # list_audio_devices()
    record()

from google import genai
from google.genai import types
import time
import json
import os
import cv2
import re
import argparse
from dotenv import load_dotenv
from PIL import Image
import io

load_dotenv()

# Initialize the client
client = genai.Client()

# Constants
TARGET_FPS = 15  # Gemini's optimal sampling rate


def convert_to_target_fps(input_path, output_dir, target_fps=15):
    """Convert video to target FPS for Gemini processing."""
    output_path = os.path.join(output_dir, f"video_{target_fps}fps.mp4")
    
    cap = cv2.VideoCapture(input_path)
    original_fps = cap.get(cv2.CAP_PROP_FPS)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    print(f"Original video: {original_fps} FPS, {width}x{height}")
    
    if abs(original_fps - target_fps) < 1:
        print(f"Video already at ~{target_fps} FPS, skipping conversion")
        cap.release()
        return input_path, original_fps
    
    frame_interval = int(round(original_fps / target_fps))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, target_fps, (width, height))
    
    frame_count = 0
    written_count = 0
    
    print(f"Converting to {target_fps} FPS (keeping every {frame_interval} frames)...")
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_count % frame_interval == 0:
            out.write(frame)
            written_count += 1
        frame_count += 1
    
    cap.release()
    out.release()
    
    print(f"Converted: {frame_count} frames -> {written_count} frames at {target_fps} FPS")
    print(f"Saved to: {output_path}")
    
    return output_path, target_fps


def extract_frame(video_path, timestamp_seconds, output_path, target_fps):
    """Extract a single frame from video at given timestamp."""
    cap = cv2.VideoCapture(video_path)
    frame_number = int(timestamp_seconds * target_fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
    ret, frame = cap.read()
    cap.release()
    if ret:
        cv2.imwrite(output_path, frame)
        print(f"Extracted: {timestamp_seconds}s -> {output_path}")
        return True
    print(f"Failed: {timestamp_seconds}s")
    return False


def get_static_element_prompt(enemy_name):
    """Generate the static element analysis prompt with enemy name injected."""
    return f"""
Analyze this 2D game video footage and identify the {enemy_name} sprite.

Your task is to find STATIC VISUAL ELEMENTS of {enemy_name}'s sprite - parts that remain visually identical across:
- All animation states (idle, attack, hit, movement animations)
- Position changes (as the enemy moves around the screen)
- Scale changes (if the enemy grows/shrinks)
- Rotation changes (if the enemy rotates)
- Background changes (the element stays the same even if background varies)

CRITICAL REQUIREMENT:
The elements don't have to be full elements, they can be asymmetrical parts of a sprite as long as they are static and distinct to {enemy_name}'s sprite, we will be using this as a reference to draw a bounding box INSIDE the element you specify, so it shouldn't be affected by background or anything else.

OUTPUT FORMAT (JSON):
Return a JSON object with this structure:
{{
  "enemy_description": "Brief description of {enemy_name}",
  "static_elements": [
    {{
      "timestamp_seconds": 1.5,
      "element_description": "Exact visual description of the SOLID static element",
      "why_static": "Why this element remains unchanged",
      "why_solid": "Confirm this element is solid/filled"
    }}
  ],
  "rotation_only_elements": [],
  "recommended_extraction_frames": [
    {{
      "timestamp_seconds": 2.0,
      "reason": "Why this frame is ideal for extraction"
    }}
  ]
}}
"""


def get_crop_from_flash(image_bytes, element_description, output_dir):
    """Call Gemini Flash to get a cropped reference image of the element."""
    prompt = f"""
I need a precise, tight crop of the INSIDE of {element_description}. Please follow these steps using the code interpreter:
1. Coordinate Detection: Identify the normalized coordinates [ymin, xmin, ymax, xmax] for {element_description} on a scale of 0 to 1000.
2. Zoom & Verify: First, use Python to create a medium-range 'zoom' crop of the area to confirm the object's exact pixel boundaries.
3. Refined Crop: Based on that zoom, calculate a final, tight bounding box that sits on the edges of the object.
4. Inward Buffer: Calculate a 'Safe Interior Box'. Ensure that NO edge pixels, borders, or background elements are included in the crop.
5. Execution: Use the PIL library to crop the original image using these refined coordinates and save it as 'final_crop.png'.
"""
    
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            types.Part(
                inline_data=types.Blob(
                    data=image_bytes,
                    mime_type="image/png"
                )
            ),
            types.Part(text=prompt)
        ],
        config=types.GenerateContentConfig(
            tools=[types.Tool(code_execution=types.ToolCodeExecution())]
        )
    )
    
    # Extract the last image from response
    last_image = None
    for part in response.candidates[0].content.parts:
        if part.text is not None:
            print(part.text)
        if part.executable_code is not None:
            print(f"[CODE] {part.executable_code.code[:200]}...")
        if part.code_execution_result is not None:
            print(f"[RESULT] {part.code_execution_result.output[:200]}...")
        try:
            img = part.as_image()
            if img is not None:
                last_image = img
        except:
            pass
    
    if last_image is not None:
        output_path = os.path.join(output_dir, "reference_crop.png")
        with open(output_path, 'wb') as f:
            f.write(last_image.image_bytes)
        print(f"\n=== SAVED REFERENCE CROP: {output_path} ===")
        return output_path
    
    print("No image returned from Flash")
    return None


def run_pipeline(video_path, enemy_name):
    """Run the full extraction pipeline."""
    # Create output directory based on enemy name
    safe_enemy_name = re.sub(r'[^\w\-_]', '_', enemy_name)
    output_dir = os.path.join("extraction_stuff", safe_enemy_name)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"\n{'='*50}")
    print(f"Extracting reference for: {enemy_name}")
    print(f"Video: {video_path}")
    print(f"Output: {output_dir}")
    print(f"{'='*50}\n")
    
    # Step 1: Convert video to target FPS
    video_for_gemini, actual_fps = convert_to_target_fps(video_path, output_dir, TARGET_FPS)
    
    # Step 2: Upload video to Gemini
    print("\nUploading video to Gemini...")
    myfile = client.files.upload(file=video_for_gemini)
    print(f"File uploaded: {myfile.name}")
    
    while myfile.state.name == "PROCESSING":
        print("Processing video...")
        time.sleep(5)
        myfile = client.files.get(name=myfile.name)
    
    if myfile.state.name == "FAILED":
        raise ValueError(f"File processing failed: {myfile.state.name}")
    
    print(f"File ready: {myfile.uri}")
    
    # Step 3: Get static element analysis from Gemini Pro
    prompt = get_static_element_prompt(enemy_name)
    
    print("\nAnalyzing video with Gemini Pro...")
    response = client.models.generate_content(
        model="gemini-3-pro-preview",
        contents=types.Content(
            parts=[
                types.Part(
                    file_data=types.FileData(file_uri=myfile.uri),
                    video_metadata=types.VideoMetadata(fps=TARGET_FPS)
                ),
                types.Part(text=prompt)
            ]
        )
    )
    
    print("\n" + "="*50)
    print("GEMINI PRO RESPONSE:")
    print("="*50)
    print(response.text)
    
    # Parse JSON response
    response_text = response.text.strip()
    json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
    if json_match:
        response_text = json_match.group(1).strip()
    else:
        json_match = re.search(r'(\{[\s\S]*\})', response_text)
        if json_match:
            response_text = json_match.group(1).strip()
    
    try:
        result = json.loads(response_text)
    except json.JSONDecodeError:
        print("Failed to parse JSON response.")
        return None
    
    # Save JSON result
    json_path = os.path.join(output_dir, "static_elements.json")
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved analysis to {json_path}")
    
    # Step 4: Extract recommended frame
    frames_dir = os.path.join(output_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    
    frame_path = None
    for i, frame_info in enumerate(result.get("recommended_extraction_frames", [])):
        ts = frame_info.get("timestamp_seconds")
        if ts is not None:
            frame_path = os.path.join(frames_dir, f"frame_{ts}s.png")
            if extract_frame(video_for_gemini, ts, frame_path, TARGET_FPS):
                break
    
    if frame_path is None or not os.path.exists(frame_path):
        print("No frames extracted")
        return None
    
    # Step 5: Get crop from Gemini Flash
    element_desc = None
    if result.get("static_elements"):
        element_desc = result["static_elements"][0].get("element_description")
    
    if element_desc is None:
        element_desc = f"the {enemy_name} sprite"
    
    print(f"\nGetting crop for: {element_desc}")
    
    # Load frame at original resolution
    img = cv2.imread(frame_path)
    _, png_bytes = cv2.imencode('.png', img)
    
    reference_path = get_crop_from_flash(png_bytes.tobytes(), element_desc, output_dir)
    
    return reference_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract enemy sprite reference for tracking")
    parser.add_argument("--video", "-v", required=True, help="Path to video file")
    parser.add_argument("--enemy", "-e", required=True, help="Name of the enemy to track")
    
    args = parser.parse_args()
    
    result = run_pipeline(args.video, args.enemy)
    
    if result:
        print(f"\n{'='*50}")
        print(f"SUCCESS! Reference crop saved to:")
        print(f"  {result}")
        print(f"{'='*50}")
    else:
        print("\nFailed to extract reference crop")


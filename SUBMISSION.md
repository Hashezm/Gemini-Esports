# Gemini Game Agent

## Inspiration

I've wanted to build an AI agent that can play video games for months. Not a simple bot that follows hardcoded rules — a system that can *watch* a game, *understand* what's happening, and *learn* to get better.

My first instinct was Gemini's LiveAPI. It has decent reaction time, it can process a video stream, and I could give it keyboard/mouse tools. So I built a full LiveAPI setup: constant screen capture at 1 FPS, tool declarations for every keyboard key, a planning system with Gemini 3 Pro for high-level goals and LiveAPI for real-time execution.

And it... kind of worked. LiveAPI could navigate menus, walk around, do basic tasks. But when I tried anything requiring precision — clicking on a specific block, aiming at an enemy, dodging an attack — it fell apart. The multimodal perception just wasn't strong enough to translate pixel positions into accurate mouse movements, even when told exactly what to do. And then I discovered LiveAPI only processes at most **one frame per second**. That's not fast enough for real-time combat. Not even close.

All those hours reading LiveAPI docs and contributing to the forums felt wasted. But then I thought: *hackers and bots in games react instantly because they have access to the game's internal state — enemy positions, health bars, all of it. What if Gemini could build its own game state from pixels?*

That reframing changed everything.

## How I Built It

I split the problem into what AI is slow at (real-time perception) and what AI is exceptional at (reasoning, code generation, learning from mistakes).

### Phase 1: AI-Powered Perception Pipeline

The agent starts with zero knowledge of the game. Given a video of an enemy:

1. **Gemini 3 Pro** analyzes the footage and identifies the most trackable static part of the enemy's sprite (e.g., "the golden crown stays consistent across animation frames")
2. **Gemini 3 Flash with code execution** takes Pro's description and writes + runs Python code on a video frame to crop the exact sprite region — pixel-perfect extraction
3. That cropped sprite feeds into a **real-time template matching tracker** I implemented based on [an MIT research paper by Elizabeth Shen](https://dspace.mit.edu/handle/1721.1/153834), running at 30+ FPS with zero training
4. Entity positions stream into a shared `game_state` object — live enemy coordinates, updated every ~33ms, no game API needed

### Phase 2: Gemini Writes the Combat AI

With real-time positions available, Gemini 3 Pro writes a complete Python combat program:

```python
def run(game_state, actions):
    entities = game_state.get_found_entities()
    for name, entity in entities.items():
        if "empress" in name.lower():
            # Kite away from the boss
            if entity["x"] > PLAYER_X:
                actions.move_left()
                actions.dash_left()
            else:
                actions.move_right()
                actions.dash_right()
            # Attack while evading
            actions.attack_at(entity["x"], entity["y"])
```

This script executes **30 times per second**, reacting to the live game state. The action system is non-blocking and intent-based — the AI can move, fly, attack, and dash *simultaneously* in a single frame with no performance penalty.

### Phase 3: The Learning Loop

Here's where it gets interesting. After each fight attempt:

1. The fight is **screen-recorded** and uploaded via the Files API
2. Gemini 3 Pro **watches the recording** and analyzes what happened — "I'm getting hit by the horizontal lance sweep because my vertical evasion timing is too slow"
3. Gemini writes an **improved combat script** incorporating its analysis
4. The new script is **hot-reloaded** (via `importlib`) and the next fight begins automatically

This is a genuine learning loop. The AI isn't retrying the same thing — it's reasoning about game mechanics, diagnosing its own failures from video evidence, and writing progressively better strategies.

### General Task System

For non-combat tasks (navigation, mining, exploration), the agent uses a planner-executor architecture:
- **Gemini 3 Pro** plans high-level subtasks and dynamically generates tools
- **Gemini 3 Flash** executes subtasks with screenshot-based feedback

The system auto-detects whether a goal is combat-related and routes to the appropriate pipeline.

## Challenges

**LiveAPI's limitations were humbling.** I spent significant time building a full LiveAPI game-playing setup — screen capture, tool declarations, planning integration — only to discover that 1 FPS and imprecise spatial understanding made it fundamentally unsuitable for real-time gameplay. The pivot to "build our own perception" was born from frustration.

**The blocking action problem.** My initial action system used `time.sleep()` for movement duration (e.g., "move left for 0.3 seconds"). This meant the script could only do one thing at a time — it couldn't move and attack simultaneously. At 30 FPS, a single 0.1s sleep wastes 3 entire frames. I had to completely redesign the system into a non-blocking, intent-based architecture where scripts declare *what they want* each frame, and a single `flush()` call applies everything in ~5ms.

**Sprite extraction reliability.** Getting Gemini to consistently identify and crop the right part of an enemy sprite was tricky. The enemy animates, rotates, glows — most of the sprite changes frame to frame. The key insight was asking Pro to find the *most static* element (like a crown or core body part), then using Flash's code execution to do the precise pixel-level cropping. This two-model handoff made extraction reliable.

**Fight termination detection.** How does the AI know when a fight is over? The boss might fly offscreen temporarily, or die, or the player might die. I used tracker-based detection: if the boss entity disappears from the game state for 15+ seconds, the fight is considered over. Simple, but it works without any game API.

## What I Learned

The biggest lesson: **the right architecture matters more than the right model.** LiveAPI with real-time video processing *sounds* like the perfect tool for game-playing AI. But splitting the problem — fast perception via computer vision, intelligent reasoning via Gemini — produced a system that's orders of magnitude more capable.

I also learned that Gemini 3's multi-model ecosystem is incredibly powerful when you orchestrate it correctly. Pro for reasoning and code generation, Flash for fast execution and code-on-images — each model has a sweet spot, and the system is greater than the sum of its parts.

Finally: **AI that writes code and then watches that code run is a fundamentally different paradigm from AI that acts directly.** The scripts Gemini writes execute at 30 FPS with zero latency. The AI doesn't need to be fast — it just needs to be *smart enough* to write fast code.

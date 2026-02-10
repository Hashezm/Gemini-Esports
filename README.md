# Gemini Game Agent

**An AI agent that teaches itself to beat game bosses in real-time — zero integration, zero training, just Gemini.**

> One command. Gemini watches an enemy, builds its own perception system, writes a combat program, executes it at 30 FPS, watches itself fail, and writes a better one. No game API. No model fine-tuning. Just pixels and reasoning.

```bash
python agent.py --goal "Defeat the Empress of Light" --video videos/empressoflight.mp4
```

---

## What This Is

Most AI game agents today work in one of two ways:
1. **Computer-use agents** that click around one screenshot at a time (~1 FPS) — too slow for anything requiring reflexes.
2. **Reinforcement learning bots** that need thousands of hours of training and deep game integration.

This project is neither. It's a **self-improving AI agent** powered entirely by the Gemini 3 model family that:

- **Builds its own real-time perception** from raw pixels (no game API)
- **Writes complete combat programs** that execute at 30+ FPS
- **Watches itself fight, diagnoses failures, and writes better code** — a genuine learning loop
- Works on **any game visible on screen** with zero integration

## How It Works

The system has three phases, all orchestrated by Gemini:

### Phase 1: Build a Game State from Pixels

The agent has no access to the game's internals. So it builds its own:

1. **Gemini 3 Pro** analyzes a video of the enemy and identifies the most trackable static part of its sprite
2. **Gemini 3 Flash** (with code execution) crops the exact sprite region from a frame
3. The sprite feeds into a **real-time template matching tracker** (based on [this MIT research paper](https://dspace.mit.edu/handle/1721.1/153834)) running at 30+ FPS
4. Entity positions stream into a shared `game_state` object — live enemy coordinates, no game API needed

### Phase 2: Gemini Writes the Bot

With real-time positions available, Gemini 3 Pro writes a complete Python combat script:

- Movement logic, dodge conditions, attack timing
- Executes 30 times per second reacting to live `game_state`
- Uses a **non-blocking, intent-based action system** — the AI can move, fly, attack, and dash simultaneously in a single frame

### Phase 3: Gemini Watches Itself and Improves

After each fight attempt:

1. The fight is **screen-recorded** and uploaded to Gemini
2. Gemini **analyzes what went wrong** — "I'm getting hit by the dash attack because I dodge too late"
3. Gemini **writes an improved script** incorporating its analysis
4. The new script is **hot-reloaded** and the next attempt begins automatically

This loop continues until the boss is defeated or max attempts are reached.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        agent.py                             │
│   Detects task type → routes to combat or general pipeline  │
├─────────────────────────┬───────────────────────────────────┤
│   General Tasks         │         Combat Tasks              │
│   (Orchestrator + Exec) │      (CombatLearner)              │
│                         │                                   │
│   Pro plans subtasks    │  ┌─ Extraction Pipeline ──────┐   │
│   Flash executes them   │  │  Pro analyzes video         │   │
│   Screenshot feedback   │  │  Flash crops sprite         │   │
│                         │  └─────────────┬───────────────┘   │
│                         │                ▼                   │
│                         │  ┌─ Tracker Service ──────────┐   │
│                         │  │  Template matching @ 30 FPS │   │
│                         │  │  → game_state (positions)   │   │
│                         │  └─────────────┬───────────────┘   │
│                         │                ▼                   │
│                         │  ┌─ Fight Loop ───────────────┐   │
│                         │  │  Pro writes combat script   │   │
│                         │  │  Script runs @ 30 FPS       │   │
│                         │  │  Screen recording           │   │
│                         │  │  Pro analyzes fight video   │   │
│                         │  │  Pro writes improved script │   │
│                         │  │  Repeat until victory       │   │
│                         │  └────────────────────────────┘   │
└─────────────────────────┴───────────────────────────────────┘
```

### Key Components

| File | Purpose |
|------|---------|
| `agent.py` | Unified entry point — routes goals to the right pipeline |
| `combat_learner.py` | Orchestrates the full fight-analyze-improve loop |
| `static_element_extraction_pipeline.py` | Gemini Pro + Flash extract trackable sprites from video |
| `tracker_service.py` | Runs real-time template matching in a background thread |
| `simple_match.py` | High-performance multi-template tracker (30+ FPS) |
| `script_runner.py` | Hot-reloads and executes AI-generated scripts every frame |
| `actions.py` | Non-blocking, intent-based input system (move + attack + dash in one frame) |
| `game_state.py` | Thread-safe shared state for entity positions |
| `screen_recorder.py` | Records fights for Gemini to analyze |
| `orchestrator.py` | Gemini Pro planner for general (non-combat) tasks |
| `executor.py` | Gemini Flash executor for general subtasks |

---

## Gemini 3 Features Used

- **Gemini 3 Pro — Video Understanding**: Analyzes enemy footage to identify attack patterns, static sprite elements, and fight outcomes
- **Gemini 3 Pro — Code Generation**: Writes complete, executable combat scripts with movement logic, dodge timing, and attack coordination
- **Gemini 3 Pro — Multi-turn Reasoning**: Maintains a persistent chat session across fight attempts, building on prior analysis to iteratively improve strategies
- **Gemini 3 Flash — Code Execution on Images**: Precisely crops sprite references from video frames using generated code
- **Gemini 3 Pro — Planning & Tool Creation**: For general tasks, plans subtasks and dynamically generates tools
- **Files API**: Uploads fight recordings for frame-by-frame video analysis
- **Multi-model orchestration**: Pro for reasoning/planning, Flash for fast execution subtasks

---

## Setup

### Requirements
- Windows 10/11 (uses `pydirectinput` for input simulation)
- Python 3.10+
- A game running in windowed/borderless mode

### Install

```bash
git clone https://github.com/YOUR_USERNAME/gemini-game-agent.git
cd gemini-game-agent
pip install -r requirements.txt
```

### Configure

```bash
cp .env.example .env
# Edit .env and add your Google API key
```

Get your API key from [Google AI Studio](https://aistudio.google.com/apikey).

### Run

**Combat mode** (boss fights with real-time learning):
```bash
cd game_agent
python agent.py --goal "Defeat the Empress of Light" --video videos/empressoflight.mp4
```

**General mode** (navigation, mining, etc.):
```bash
cd game_agent
python agent.py --goal "Dig down to find a cave"
```

**Direct combat learner** (skip the agent router):
```bash
cd game_agent
python combat_learner.py --enemy "Empress of Light" --video videos/empressoflight.mp4 --max-attempts 10
```

---

## What Makes This Different

| | Traditional Bots | RL Agents | Computer-Use AI | **This Project** |
|---|---|---|---|---|
| Game integration | Memory reading / API | Custom environment | Screenshots | **Pixels only** |
| Reaction time | Instant | Instant | ~1-2 seconds | **~33ms (30 FPS)** |
| Training required | Manual scripting | Thousands of hours | None | **None** |
| Can learn from failure | No | Yes (reward signal) | No | **Yes (video analysis)** |
| Generates own perception | No | No | No | **Yes** |
| Writes own programs | No | No | No | **Yes** |

---

## Project Structure

```
├── game_agent/               # Core agent code
│   ├── agent.py              # Main entry point
│   ├── combat_learner.py     # Fight-analyze-improve loop
│   ├── actions.py            # Non-blocking input system
│   ├── game_state.py         # Shared entity state
│   ├── script_runner.py      # Script hot-reloader
│   ├── tracker_service.py    # Background tracking service
│   ├── screen_recorder.py    # Fight recording
│   ├── static_element_extraction_pipeline.py  # Sprite extraction
│   ├── orchestrator.py       # Pro planner (general tasks)
│   ├── executor.py           # Flash executor (general tasks)
│   └── test_scripts/         # AI-generated combat scripts
├── 2dgametest/               # Computer vision tracking
│   └── simple_match.py       # Multi-template tracker (30+ FPS)
├── my scripts/               # LiveAPI experiments & prototypes
├── old/                      # Early prototypes
├── requirements.txt
└── .env.example
```

---

## Built for the Gemini 3 Hackathon

This project demonstrates that Gemini 3 isn't just a chatbot — it's a reasoning engine capable of building its own perception, writing its own programs, and genuinely learning from experience. The same architecture that fights game bosses could extract data from any visual interface, automate any screen-based workflow, or operate any system that humans interact with through pixels.

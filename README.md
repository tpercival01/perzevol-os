# ⚡ VCT Draft Analyst: AI-Powered Valorant Draft Assistant

A Streamlit-based Valorant draft assistant that combines professional VCT composition data, rule-based validation, and deterministic LLM prompting to recommend agent picks under ranked pressure.

Created by [Thomas Percival](https://linkedin.com/in/thomaspercival)  
Video demo: Coming 10 May 2026

> **Status:** Open to remote Python, backend, data, automation, and applied AI engineering roles.

---

## Overview

VCT Draft Analyst is an experimental AI/gaming project built for the first Perzevol video.

The system analyses professional Valorant team compositions and uses a constrained LLM layer to recommend ranked agent picks based on:

- selected map
- teammate instalocks
- available agents
- role balance
- pro-play composition patterns
- panic/failsafe conditions

The goal is not to “solve” Valorant drafting perfectly. The goal is to test whether a data-driven assistant can reduce emotional decision-making during ranked agent select.

---

## Key Features

- **VCT data pipeline:** Uses pandas to process pro-play composition data into map-specific meta summaries.
- **Constraint-aware recommendations:** Combines role rules, teammate picks, and available agents.
- **Deterministic LLM prompting:** Uses low-temperature Groq/LLaMA calls with strict output formatting.
- **Failsafe mode:** Detects poor team states, such as four duelists, and recommends damage-control picks.
- **Streamlit dashboard:** Local UI for map selection, roster state, agent locks, and recommendations.
- **JSON state management:** Stores user roster and draft state locally.

---

## System Architecture

```text
Raw VCT Data
     ↓
Pandas Cleaning / Aggregation
     ↓
Map Meta Matrix
     ↓
Rule-Based Draft Validation
     ↓
Constrained LLM Recommendation
     ↓
Streamlit UI Output
```

## Tech Stack
- Python 3.10+
- pandas
- Groq API (LLaMA 3)
- Streamlit
- JSON
- python-dotenv

## Quick Start
```
git clone https://github.com/tpercival01/val-ai-draft.git
cd val-ai-draft
pip install -r requirements.txt
```

Create a .env file in the root directory:

```
GROQ_API_KEY=your_api_key_here
```

Run the app:
```
streamlit run app.py
```

## Example Use Case
- Select the current Valorant map.
- Add teammate picks as they lock agents.
- Mark unavailable agents from your roster.
- Run the draft analysis.
- Receive a recommended pick and short tactical reason.

## Limitations

- The app is experimental and not an official Riot Games product.
- Recommendations depend on the quality and freshness of the input data.
- The LLM layer is constrained, but not infallible.
- Ranked solo queue contains variables the system cannot control, including smurfs, teammate behaviour, aim disparity, and communication quality.
- The current version prioritises clarity and speed over deep simulation.

## Roadmap

This project is Module 01 of Perzevol OS, a planned suite of AI/gaming tools built publicly through YouTube videos.

## Planned modules include:

| Module | Project |
|---:|---|
| 01 | Valorant Draft Analyst |
| 02 | CS2 Timing/Metronome Tool |
| 03 | Warzone Loadout Optimiser |
| 04 | TBD |
| 05 | TBD |
| 06 | Perzevol OS Suite Launch |

## About

Built by Thomas Percival as a public proof-of-work project combining Python, applied AI, gaming analytics, and product storytelling.

LinkedIn: https://linkedin.com/in/thomaspercival

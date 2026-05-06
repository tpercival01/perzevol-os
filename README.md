# ⚡ Perzevol.OS: The Algorithmic Gaming Suite

A modular, Streamlit-based operating system designed to mathematically "solve" competitive multiplayer games using Python, live data scraping, and deterministic AI prompting. 

Created by [Thomas Percival](https://linkedin.com/in/thomaspercival)
Video logs and development updates available on YouTube.

> **Status:** Actively building in public. Open to remote Python, backend, data, automation, and applied AI engineering roles.

---

## Overview

Perzevol.OS is an experimental data science and gaming project. Instead of relying on mechanical reflexes or human intuition, this suite provides algorithmic external advisors for chaotic ranked environments.

Built as a centralized hub, the application expands incrementally. Every fortnight, a new module is engineered and deployed to test a specific mathematical hypothesis in a different competitive arena.

The goal is not to execute perfect game simulations. The goal is to prove that structured data pipelines, pure geometry, and constrained large language models can overcome emotional decision making and mechanical skill deficits in low ELO lobbies.

---

## Active Modules

### 🟢 Module 01: VCT Draft Analyst (Valorant)
*Status: Live (Released 10 May 2026)*

Analyses professional VCT team compositions and uses a constrained LLM layer to recommend mathematically optimal ranked agent picks.
- **Data Pipeline:** Uses Pandas to process global pro-play composition data into map-specific meta matrices.
- **Logic Engine:** Combines role rules, teammate picks, and available roster constraints via JSON state management.
- **Failsafe System:** Detects catastrophic team states (e.g. four Duelists) and executes a damage control override.
- **Output:** Low-temperature Groq (LLaMA 3) calls spoon-fed with Python logic to generate zero-creativity, purely tactical directives.

### ⏳ Future Modules (In Development)
Check the Roadmap section below for upcoming system integrations.

---

## System Architecture

Perzevol.OS relies on a modular Streamlit architecture. New games or tools are isolated into independent pages while sharing core environment variables and styling logic.

```text
External APIs / Raw Datasets
           ↓
Python Parsing & Aggregation
           ↓
      Perzevol.OS 
 ┌─────────┴─────────┐
 │                   │
Mod 01 (Val)      Mod 02 (CS2) ... (Subsequent Modules)
 │                   │
Groq LLM        Physics Math
 │                   │
 └─────────┬─────────┘
           ↓
   Streamlit Master UI
           ↓
   Hardware / Screen Output
```

## Tech Stack
- **Core:** Python 3.12+
- **Frontend / UI:** Streamlit (Multi-page configuration)
- **AI Processing:** Groq API (LLaMA 3 70B Versatile)
- **Data Manipulation:** Pandas, Native JSON
- **Environment:** python-dotenv

---

## Quick Start

Clone the repository and install the dependencies to run the local dashboard.

```bash
git clone https://github.com/tpercival01/perzevol-os.git
cd perzevol-os
pip install -r requirements.txt
```

Create a `.env` file in the root directory for the API modules:

```text
GROQ_API_KEY=your_api_key_here
```

Launch the operating system:

```bash
streamlit run Home.py
```

---

## Limitations and Compliance

- **Vanguard Safe:** Perzevol.OS uses external read-only data, manual input ledgers, or mathematical overlays. It does not inject code into game clients or automate prohibited keystrokes.
- **Experimental Output:** Recommendations depend heavily on the quality and freshness of the input data APIs. 
- **Ranked Chaos:** Algorithmic logic cannot account for smurfs, server connectivity issues, or unpredictable human behaviour in solo queue lobbies.

---

## Development Roadmap

This centralized hub serves as the backbone for the Perzevol YouTube channel. New tools are added as they are tested and deployed in video formats.

| Status | Module | Target Engine | Core Tech Focus |
| :--- | :--- | :--- | :--- |
| **Complete** | 01: The Draft AI | Valorant | Pandas Data Pipelines & Groq LLM |
| **Planned** | 02: The Metronome | Counter-Strike 2 | Deceleration Physics & Rhythmic Math |
| **Planned** | 03: The Blacksmith | Call of Duty: Warzone | API Web Scraping & Combinatorial Optimization |
| **Planned** | 04: The Commander | General Voice Comms | ElevenLabs Voice Synthesis & Audio Routing |
| **Planned** | 05: The Vector | Apex Legends | Spatial Geometry & Stereo Audio Calculation |
| **Planned** | 06: Public Launch | Full Server Deployment | Cloud Hosting & User Authentication |

---

## About the Developer

Built by Thomas Percival as a public proof-of-work laboratory. This project sits at the intersection of Python engineering, applied AI, statistical gaming analytics, and product storytelling.

**Connect & Follow:**
- **LinkedIn:** [https://linkedin.com/in/thomaspercival](https://linkedin.com/in/thomaspercival)

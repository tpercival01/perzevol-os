# ⚡ VCT Draft Analyst: LLM-Powered Esports Tactics

An AI orchestration engine that ingests professional Valorant Champions Tour (VCT) data to generate deterministic, mathematically optimal team compositions in real-time.

Created by [Thomas Percival](https://linkedin.com/in/thomaspercival) | [Watch the build & gameplay video here] (Link coming soon)

> **Status:** Open to remote Python Backend & AI Engineering roles or high-value freelance contracts.

## 🧠 System Architecture

A structured AI pipeline built to enforce strict constraints:

1. **Data Ingestion (`data_pipeline.py`):** Uses Pandas to aggregate thousands of rows of global VCT match data, calculating pick rates and map confidences to build a JSON meta-matrix.
2. **Deterministic LLM Orchestration (`groq_engine.py`):** Feeds the matrix into LLaMA-3 via Groq. The prompt engineering explicitly restricts the model to returning highly constrained, two-line JSON/text outputs, eliminating hallucination.
3. **Failsafe Logic:** Hardcoded Python fallback logic triggers an override if user constraints (e.g., locking 4 duelists) create an unsalvageable environment, forcing the LLM to recommend a self-sufficient carry agent.
4. **Local Dashboard (`app.py`):** A Streamlit interface handling state management, user account unlocks, and real-time AI API requests.

## 🛠️ Tech Stack

- **Language:** Python 3.10+
- **Data Engineering:** Pandas
- **AI/LLM:** Groq API, LLaMA-3 (Strict Prompt Engineering, Temperature 0.0)
- **Frontend:** Streamlit
- **Environment:** python-dotenv

## 🚀 Quick Start

```bash
git clone https://github.com/tpercival01/val-ai-draft.git
cd val-ai-draft
pip install -r requirements.txt
```

_Create a `.env` file in the root directory and add your `GROQ_API_KEY`._

```bash
streamlit run app.py
```

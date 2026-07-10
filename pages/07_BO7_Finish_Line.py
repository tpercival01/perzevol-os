from __future__ import annotations

import html
from datetime import date
from pathlib import Path
from typing import Any

import streamlit as st

from modules.ui.perzevol_theme import inject_perzevol_theme

from modules.warzone.killchain_engine import (
    compute_full_tracker_summary,
    load_tracker_tasks,
    summarise_tasks,
)
from modules.warzone.series_director import (
    default_deadline_date,
    days_until,
    parse_date,
)

st.set_page_config(
    page_title="Perzevol OS - BO7 Finish Line",
    page_icon="🏁",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_perzevol_theme(screen="finish_line")


CLEAN_FOLDER = Path("data/bo7_clean")

TRUE_STATUS = {"TRUE", "YES", "DONE", "COMPLETE", "COMPLETED", "✅"}
RESOLVED_STATUSES = {"done", "partial", "skipped"}


def clean(value: Any) -> str:
    return str(value or "").strip()


def esc(value: Any) -> str:
    return html.escape(clean(value))


def compact_markup(markup: str) -> str:
    return "".join(
        line.strip()
        for line in str(markup or "").splitlines()
        if line.strip()
    )


def render_html(markup: str):
    st.markdown(compact_markup(markup), unsafe_allow_html=True)


def pct(done: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return max(0.0, min(100.0, (done / total) * 100))


def display_pct(done: int, total: int) -> str:
    if total <= 0:
        return "NO DATA"
    return f"{pct(done, total):.1f}%"


def pair_done_total(value: Any) -> tuple[int, int]:
    if isinstance(value, dict):
        total_block = value.get("total")
        if isinstance(total_block, dict):
            return int(total_block.get("done", 0) or 0), int(total_block.get("total", 0) or 0)

        return int(value.get("done", 0) or 0), int(value.get("total", 0) or 0)

    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return int(value[0] or 0), int(value[1] or 0)

    return 0, 0


def bucket(label: str, done: int, total: int, group: str, note: str = "") -> dict[str, Any]:
    return {
        "label": label,
        "done": int(done or 0),
        "total": int(total or 0),
        "group": group,
        "note": note,
        "percent": pct(int(done or 0), int(total or 0)),
    }


def sum_buckets(buckets: list[dict[str, Any]]) -> tuple[int, int]:
    return (
        sum(int(item.get("done", 0) or 0) for item in buckets),
        sum(int(item.get("total", 0) or 0) for item in buckets),
    )


def completion_buckets(summary: dict[str, Any]) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []

    camos = summary.get("camos", {}) or {}
    for label, data in camos.items():
        if not isinstance(data, dict):
            continue

        true_final_done = int(data.get("mastery_done", 0) or 0)
        true_final_total = int(data.get("mastery_total", 0) or 0)
        done = int(data.get("mastery_unlock_done", min(true_final_done, 30)) or 0)
        total = int(data.get("mastery_unlock_total", 30) or 30)
        base_done = int(data.get("base_done", 0) or 0)
        base_total = int(data.get("base_total", 0) or 0)

        buckets.append(
            bucket(
                label=f"{label} 30 top camos",
                done=done,
                total=total,
                group="Camos",
                note=(
                    "DONE target is 30, not every weapon. "
                    f"All-weapons reference: {true_final_done}/{true_final_total}. "
                    f"Base chain: {base_done}/{base_total}."
                ),
            )
        )

    prestige = summary.get("prestige", {}) or {}
    prestige_stages = prestige.get("stages", {}) if isinstance(prestige, dict) else {}
    if isinstance(prestige_stages, dict) and prestige_stages:
        done = 0
        total = 0
        for stage in prestige_stages.values():
            stage_done, stage_total = pair_done_total(stage)
            done += stage_done
            total += stage_total
        buckets.append(
            bucket(
                "Weapon Prestige",
                done,
                total,
                "Weapon Progression",
                "Prestige 1, Prestige 2, WPM, then levels 100 / 150 / 200 / 250.",
            )
        )

    mastery = summary.get("mastery_badges", {}) or {}
    if isinstance(mastery, dict):
        weapon_done, weapon_total = pair_done_total(mastery.get("weapon", {}))
        buckets.append(
            bucket(
                "Weapon Mastery Badges",
                weapon_done,
                weapon_total,
                "Mastery Badges",
                "Multiplayer and Zombies weapon badge progression.",
            )
        )

        support_done, support_total = pair_done_total(mastery.get("support", {}))
        buckets.append(
            bucket(
                "Equipment / Scorestreak Mastery Badges",
                support_done,
                support_total,
                "Mastery Badges",
                "MP and Zombies support badges, including equipment and scorestreak-style rows.",
            )
        )

    reticles = summary.get("reticles", {}) or {}
    reticle_done, reticle_total = pair_done_total(reticles)
    buckets.append(
        bucket(
            "Reticles",
            reticle_done,
            reticle_total,
            "Optics",
            "Stages 20, 40, 60, 80, and 100.",
        )
    )

    calling_cards = summary.get("calling_cards", {}) or {}
    if isinstance(calling_cards, dict):
        for mode, data in calling_cards.items():
            done, total = pair_done_total(data)
            buckets.append(
                bucket(
                    f"{mode} Calling Cards",
                    done,
                    total,
                    "Calling Cards",
                    "Includes counted Dark Ops if your tracker marks them as required.",
                )
            )

    titles = summary.get("titles", {}) or {}
    title_done, title_total = pair_done_total(titles)
    buckets.append(bucket("Titles", title_done, title_total, "Account Cosmetics"))

    colours = summary.get("colours", {}) or {}
    colour_done, colour_total = pair_done_total(colours)
    buckets.append(bucket("Colours", colour_done, colour_total, "Account Cosmetics"))

    aug_done, aug_total = pair_done_total(summary.get("augments", (0, 0)))
    buckets.append(
        bucket(
            "Zombies Augments",
            aug_done,
            aug_total,
            "Mode Systems",
            "Minor, major, and extra-slot augment unlocks.",
        )
    )

    oc_done, oc_total = pair_done_total(summary.get("overclocks", (0, 0)))
    buckets.append(
        bucket(
            "Multiplayer Overclocks",
            oc_done,
            oc_total,
            "Mode Systems",
            "Tracked overclock unlocks from multiplayer systems.",
        )
    )

    intel = summary.get("intel", {}) or {}
    if isinstance(intel, dict) and intel:
        done = 0
        total = 0
        for data in intel.values():
            item_done, item_total = pair_done_total(data)
            done += item_done
            total += item_total
        buckets.append(bucket("Intel", done, total, "Collectibles"))

    rewards = summary.get("rewards", {}) or {}
    if isinstance(rewards, dict):
        reward_keys = [
            ("zombies_total", "Zombies Rewards", "Rewards"),
            ("endgame_operations_total", "Endgame Operations", "Rewards"),
            ("endgame_unlocks_total", "Endgame Unlocks", "Rewards"),
        ]
        for key, label, group in reward_keys:
            done, total = pair_done_total(rewards.get(key, (0, 0)))
            buckets.append(bucket(label, done, total, group))

    return [item for item in buckets if int(item.get("total", 0) or 0) > 0]


def commander_completion_score(buckets: list[dict[str, Any]]) -> float:
    """
    This is intentionally bucket-weighted, not raw-row weighted.

    Raw rows would let giant systems dominate the headline. The Finish Line page
    is a morale and video scoreboard, so each visible bucket gets one vote.
    """
    valid = [item for item in buckets if int(item.get("total", 0) or 0) > 0]
    if not valid:
        return 0.0

    return sum(float(item["percent"]) for item in valid) / len(valid)


def status_label(item: dict[str, Any]) -> str:
    total = int(item.get("total", 0) or 0)
    if total <= 0:
        return "NO DATA"

    done = int(item.get("done", 0) or 0)
    if done >= total:
        return "DONE"

    percent = float(item.get("percent", 0) or 0)
    if percent >= 90:
        return "FINAL PUSH"
    if percent >= 60:
        return "IN MOTION"
    if percent > 0:
        return "STARTED"

    return "UNTOUCHED"


def status_class(item: dict[str, Any]) -> str:
    label = status_label(item)
    if label == "DONE":
        return "done"
    if label == "FINAL PUSH":
        return "push"
    if label == "IN MOTION":
        return "moving"
    if label == "STARTED":
        return "started"
    return "empty"


def deadline_context() -> dict[str, Any]:
    deadline = default_deadline_date()
    parsed = parse_date(deadline)
    remaining = days_until(deadline)

    if parsed:
        label = parsed.strftime("%A %d %B %Y")
    else:
        label = "Friday 23 October"

    return {
        "date": deadline,
        "label": label,
        "days": remaining,
    }


def current_session_progress() -> dict[str, int]:
    results = st.session_state.get("bo7_stop_results", {})
    if not isinstance(results, dict):
        results = {}

    done = 0
    partial = 0
    skipped = 0
    pending = 0

    plan = st.session_state.get("bo7_session_plan", {})
    stops = plan.get("stops", []) if isinstance(plan, dict) else []

    for stop in stops:
        task_id = clean(stop.get("task_id"))
        status = clean(results.get(task_id, {}).get("status")) if task_id in results else "pending"

        if status == "done":
            done += 1
        elif status == "partial":
            partial += 1
        elif status == "skipped":
            skipped += 1
        else:
            pending += 1

    return {
        "done": done,
        "partial": partial,
        "skipped": skipped,
        "pending": pending,
        "total": len(stops),
    }


def next_visible_buckets(buckets: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    unfinished = [
        item for item in buckets
        if int(item.get("total", 0) or 0) > 0
        and int(item.get("done", 0) or 0) < int(item.get("total", 0) or 0)
    ]

    unfinished.sort(
        key=lambda item: (
            float(item.get("percent", 0) or 0) == 0,
            -float(item.get("percent", 0) or 0),
            int(item.get("total", 0) or 0) - int(item.get("done", 0) or 0),
        )
    )

    return unfinished[:limit]


def render_css():
    render_html(
        """
        <style>
        [data-testid="stSidebar"] {display: none;}
        [data-testid="collapsedControl"] {display: none;}
        header {visibility: hidden;}
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}

        /*
        Finish Line is a dashboard, not a locked OBS frame.
        The shared finish_line theme used viewport locking, which clipped
        checklist cards once the tracker gained enough buckets.
        */
        html, body, .stApp {
            min-height: 100dvh !important;
            height: auto !important;
            overflow-x: hidden !important;
            overflow-y: auto !important;
        }

        .block-container {
            min-height: 100dvh !important;
            height: auto !important;
            max-height: none !important;
            overflow: visible !important;
        }

        .stApp {
            background:
                radial-gradient(circle at top left, rgba(255,75,75,0.20), transparent 30%),
                radial-gradient(circle at bottom right, rgba(48,209,88,0.14), transparent 28%),
                linear-gradient(135deg, #050608 0%, #090b10 48%, #030405 100%);
        }

        .block-container {
            max-width: 96vw;
            padding-top: 1.1rem;
            padding-bottom: 1.2rem;
            padding-left: 1.3rem;
            padding-right: 1.3rem;
        }

        .finish-hero {
            border: 1px solid rgba(255,255,255,0.12);
            background:
                radial-gradient(circle at top right, rgba(255,75,75,0.34), rgba(255,75,75,0.06) 35%, transparent 65%),
                linear-gradient(135deg, rgba(255,255,255,0.08), rgba(255,255,255,0.025));
            padding: 1.2rem 1.35rem;
            margin-bottom: 1rem;
        }

        .finish-kicker {
            color: #ff4b4b;
            font-family: monospace;
            font-size: 0.9rem;
            font-weight: 950;
            letter-spacing: 0.24em;
            text-transform: uppercase;
        }

        .finish-title {
            color: #ffffff;
            font-size: 4.6rem;
            font-weight: 950;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            line-height: 0.9;
            margin-top: 0.45rem;
        }

        .finish-subtitle {
            color: #d8d8d8;
            font-size: 1.15rem;
            margin-top: 0.8rem;
        }

        .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.65rem;
            margin-top: 1rem;
        }

        .metric {
            border: 1px solid rgba(255,255,255,0.10);
            background: rgba(0,0,0,0.32);
            padding: 0.85rem 0.9rem;
        }

        .metric-label {
            color: #9ca3af;
            font-family: monospace;
            font-size: 0.72rem;
            letter-spacing: 0.16em;
            text-transform: uppercase;
        }

        .metric-value {
            color: #ffffff;
            font-size: 2.1rem;
            font-weight: 950;
            line-height: 1;
            margin-top: 0.45rem;
        }

        .metric-note {
            color: #c7c7c7;
            font-size: 0.83rem;
            margin-top: 0.35rem;
        }

        .progress-rail {
            height: 22px;
            background: rgba(255,255,255,0.09);
            border: 1px solid rgba(255,255,255,0.12);
            margin-top: 0.8rem;
            overflow: hidden;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, rgba(255,75,75,0.95), rgba(255,214,10,0.95), rgba(48,209,88,0.95));
        }

        .section-title {
            color: #ffffff;
            font-size: 1.4rem;
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 1.1rem 0 0.65rem 0;
        }

        .check-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 0.55rem;
            max-height: none !important;
            overflow: visible !important;
        }

        .check-card {
            border: 1px solid rgba(255,255,255,0.10);
            background: rgba(255,255,255,0.035);
            padding: 0.68rem 0.72rem;
            min-height: 118px;
        }

        .check-card.done {
            border-left: 7px solid #30d158;
        }

        .check-card.push {
            border-left: 7px solid #ffd60a;
        }

        .check-card.moving {
            border-left: 7px solid #0a84ff;
        }

        .check-card.started {
            border-left: 7px solid #bf5af2;
        }

        .check-card.empty {
            border-left: 7px solid #ff4b4b;
        }

        .check-top {
            display: flex;
            justify-content: space-between;
            gap: 0.6rem;
            align-items: flex-start;
        }

        .check-label {
            color: #ffffff;
            font-size: 1.0rem;
            font-weight: 900;
            line-height: 1.1;
        }

        .check-status {
            color: #ffffff;
            background: rgba(255,255,255,0.10);
            border: 1px solid rgba(255,255,255,0.12);
            font-family: monospace;
            font-size: 0.68rem;
            font-weight: 950;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            padding: 0.22rem 0.35rem;
            white-space: nowrap;
        }

        .check-count {
            color: #ffffff;
            font-size: 1.75rem;
            font-weight: 950;
            margin-top: 0.55rem;
        }

        .check-note {
            color: #bababa;
            font-size: 0.76rem;
            margin-top: 0.3rem;
            min-height: 0;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .mini-bar {
            height: 9px;
            background: rgba(255,255,255,0.10);
            margin-top: 0.6rem;
            overflow: hidden;
        }

        .mini-fill {
            height: 100%;
            background: rgba(48,209,88,0.90);
        }

        .priority-card {
            border: 1px solid rgba(255,214,10,0.22);
            background:
                radial-gradient(circle at top right, rgba(255,214,10,0.18), transparent 45%),
                rgba(0,0,0,0.22);
            padding: 0.62rem 0.72rem;
            margin-bottom: 0.42rem;
        }

        .priority-title {
            color: #ffffff;
            font-weight: 950;
            font-size: 1rem;
        }

        .priority-meta {
            color: #cccccc;
            font-family: monospace;
            font-size: 0.78rem;
            margin-top: 0.25rem;
        }

        .quote {
            border-left: 8px solid #ff4b4b;
            background: rgba(255,75,75,0.10);
            padding: 1rem 1.1rem;
            color: #ffffff;
            font-size: 1.55rem;
            font-weight: 950;
            letter-spacing: 0.02em;
            text-transform: uppercase;
            margin-top: 0.9rem;
        }
        </style>
        """
    )


def render_hero(overall_score: float, buckets: list[dict[str, Any]], task_summary: dict[str, Any]):
    deadline = deadline_context()
    done, total = sum_buckets(buckets)
    session = current_session_progress()
    fill_width = max(0, min(100, overall_score))

    render_html(
        f"""
        <div class="finish-hero">
            <div class="finish-kicker">BO7 FINISH LINE</div>
            <div class="finish-title">{deadline["days"]} DAYS TO MW4</div>
            <div class="finish-subtitle">
                Commander completion score: <strong>{overall_score:.1f}%</strong>.
                Not official. Bucket-weighted from the systems this tracker treats as BO7 DONE.
            </div>

            <div class="progress-rail">
                <div class="progress-fill" style="width: {fill_width:.1f}%;"></div>
            </div>

            <div class="metric-grid">
                <div class="metric">
                    <div class="metric-label">Deadline</div>
                    <div class="metric-value">{esc(deadline["label"])}</div>
                    <div class="metric-note">Target pressure point.</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Completion</div>
                    <div class="metric-value">{overall_score:.1f}%</div>
                    <div class="metric-note">Bucket-weighted morale score.</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Tracker Atoms</div>
                    <div class="metric-value">{done}/{total}</div>
                    <div class="metric-note">Raw tracked checklist items counted by available CSVs.</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Current Session</div>
                    <div class="metric-value">{session["done"]}+{session["partial"]}</div>
                    <div class="metric-note">Done + partial stops in the active Mission Control plan.</div>
                </div>
            </div>

            <div class="quote">No MW4 until BO7 is done. One bucket at a time.</div>
        </div>
        """
    )


def render_priority_list(buckets: list[dict[str, Any]]):
    priorities = next_visible_buckets(buckets)

    render_html('<div class="section-title">Next visible progress for video ending</div>')

    if not priorities:
        st.success("Every visible bucket is complete. That should mean BO7 is DONE by the current tracker definition.")
        return

    for item in priorities:
        remaining = int(item["total"]) - int(item["done"])
        render_html(
            f"""
            <div class="priority-card">
                <div class="priority-title">{esc(item["label"])}</div>
                <div class="priority-meta">
                    {item["done"]}/{item["total"]} complete · {item["percent"]:.1f}% · {remaining} left
                </div>
            </div>
            """
        )


def render_checklist(buckets: list[dict[str, Any]]):
    render_html('<div class="section-title">BO7 DONE checklist</div>')

    cards = []
    for item in buckets:
        width = max(0, min(100, float(item.get("percent", 0) or 0)))
        cards.append(
            f"""
            <div class="check-card {status_class(item)}">
                <div class="check-top">
                    <div class="check-label">{esc(item["label"])}</div>
                    <div class="check-status">{status_label(item)}</div>
                </div>
                <div class="check-count">{item["done"]}/{item["total"]}</div>
                <div class="check-note">{esc(item.get("note", ""))}</div>
                <div class="mini-bar">
                    <div class="mini-fill" style="width: {width:.1f}%;"></div>
                </div>
            </div>
            """
        )

    render_html(f'<div class="check-grid">{"".join(cards)}</div>')


def render_footer(task_summary: dict[str, Any]):
    available = int(task_summary.get("available", 0) or 0)
    locked = int(task_summary.get("locked", 0) or 0)
    total = int(task_summary.get("total", 0) or 0)

    st.divider()
    st.caption(
        f"Commander task view: {available} available next-step objectives, "
        f"{locked} locked, {total} total emitted next-step objectives. "
        "The headline completion score is bucket-weighted so giant systems do not drown out smaller endgame buckets."
    )


def main():
    render_css()

    try:
        summary = compute_full_tracker_summary(CLEAN_FOLDER)
        tasks = load_tracker_tasks()
        task_summary = summarise_tasks(tasks)
    except Exception as exc:
        st.error(f"Finish Line could not read tracker data: {exc}")
        st.stop()

    buckets = completion_buckets(summary)
    overall_score = commander_completion_score(buckets)

    render_hero(overall_score, buckets, task_summary)

    left, right = st.columns([1.25, 1])

    with left:
        render_checklist(buckets)

    with right:
        render_priority_list(buckets)
        render_footer(task_summary)


main()

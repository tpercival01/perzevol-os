from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any


DEFAULT_SERIES_NAME = "BO7 Completion Before MW4"
DEFAULT_DEADLINE_MONTH = 10
DEFAULT_DEADLINE_DAY = 23


def clean(value: Any) -> str:
    return str(value or "").strip()


def default_deadline_date(today: date | None = None) -> str:
    """
    Uses October 23rd as the default MW4 pressure point without hard-coding a
    changing release claim into the app.
    """
    today = today or date.today()
    candidate = date(today.year, DEFAULT_DEADLINE_MONTH, DEFAULT_DEADLINE_DAY)

    if today > candidate:
        candidate = date(today.year + 1, DEFAULT_DEADLINE_MONTH, DEFAULT_DEADLINE_DAY)

    return candidate.isoformat()


def parse_date(value: Any) -> date | None:
    text = clean(value)

    if not text:
        return None

    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def days_until(deadline: str, today: date | None = None) -> int:
    today = today or date.today()
    parsed = parse_date(deadline)

    if not parsed:
        return 0

    return max(0, (parsed - today).days)


def task_type_label(task_type: str) -> str:
    labels = {
        "camo": "camos",
        "mastery_badge_weapon": "weapon mastery",
        "mastery_badge_equipment": "equipment mastery",
        "weapon_prestige": "weapon levels",
        "reticle": "reticles",
        "calling_card": "calling cards",
        "dark_ops": "dark ops",
        "misc_challenge": "challenges",
        "zombies_reward": "Zombies rewards",
        "endgame_operation": "Endgame operations",
        "endgame_unlock": "Endgame unlocks",
        "title": "titles",
    }
    return labels.get(clean(task_type), clean(task_type) or "completion")


def dominant_task_type(plan: dict) -> str:
    counter = Counter(
        clean(stop.get("task_type"))
        for stop in plan.get("stops", []) or []
        if clean(stop.get("task_type"))
    )

    if not counter:
        return "completion"

    return task_type_label(counter.most_common(1)[0][0])


def first_stop(plan: dict) -> dict:
    stops = plan.get("stops", []) or []
    return stops[0] if stops else {}


def first_stop_label(plan: dict) -> str:
    stop = first_stop(plan)
    weapon = clean(stop.get("weapon")) or "the first objective"
    camo = clean(stop.get("camo")) or "the target"
    return f"{weapon} - {camo}"


def pressure_label(days_remaining: int) -> str:
    if days_remaining <= 0:
        return "Deadline live"
    if days_remaining <= 14:
        return "Redline"
    if days_remaining <= 30:
        return "High pressure"
    if days_remaining <= 60:
        return "Building pressure"
    return "On pace"


def series_target_defaults(today: date | None = None) -> dict:
    deadline = default_deadline_date(today)
    return {
        "series_name": DEFAULT_SERIES_NAME,
        "deadline_date": deadline,
        "deadline_label": "MW4 October target",
    }


def normalise_target(target: dict | None = None, today: date | None = None) -> dict:
    defaults = series_target_defaults(today)
    target = target or {}

    return {
        "series_name": clean(target.get("series_name")) or defaults["series_name"],
        "deadline_date": clean(target.get("deadline_date")) or defaults["deadline_date"],
        "deadline_label": clean(target.get("deadline_label")) or defaults["deadline_label"],
    }


def completion_progress_line(task_summary: dict | None, completion_state: dict | None) -> str:
    task_summary = task_summary or {}
    completion_state = completion_state or {}

    available = task_summary.get("available", 0)
    locked = task_summary.get("locked", 0)
    total = task_summary.get("total", 0)
    completed = len(completion_state)

    if total or available or locked or completed:
        return (
            f"Tracker state: {available} available next-step objectives, "
            f"{locked} locked, {completed} app-logged completions."
        )

    return "Tracker state will update from Mission Control after progress is logged."


def hook_for_plan(plan: dict, mode: str, energy: str, focus: str) -> str:
    quick_mode = clean(plan.get("quick_mode_label"))
    commander_mode = clean(plan.get("commander_mode"))

    if "Low" in energy:
        return f"AI chose a low-energy {mode} route to bank BO7 completion without a decision spiral."

    if "High" in energy:
        return f"AI forced a high-energy {mode} push to attack the BO7 completion backlog before MW4."

    if quick_mode == "Tracker Cleanup" or commander_mode == "Closest finishes":
        return "AI hunted the closest BO7 unlocks left in the tracker and banned rerolls."

    if focus != "completion":
        return f"AI built a {mode} route around {focus}, then stacked the loadout around it."

    return f"I gave the BO7 grind to the Commander. It picked {mode}, the route, and the loadout."


def episode_title_for_plan(plan: dict, mode: str, energy: str, focus: str) -> str:
    if "Low" in energy:
        return f"AI Chose My Low Energy {mode} Grind"

    if "High" in energy:
        return f"Brute Forcing {mode} Completion Before MW4"

    if clean(plan.get("quick_mode_label")) == "Tracker Cleanup":
        return "AI Found the Closest BO7 Unlocks"

    return f"AI Chose My BO7 {mode} Completion Route"


def thumbnail_text_for_plan(mode: str, energy: str) -> str:
    if "Low" in energy:
        return f"LOW ENERGY {mode.upper()}"

    if "High" in energy:
        return f"NO REROLL {mode.upper()}"

    return f"AI CHOSE {mode.upper()}"


MORALE_BANK = {
    "drill": [
        {
            "headline": "NO MW4 UNTIL THIS IS DONE.",
            "line": "The whole tracker is not tonight's problem. Tonight's problem is the next proof screen.",
            "rule": "No menu spirals. Queue the assigned route, bank one measurable thing, then reassess.",
        },
        {
            "headline": "ONE CHALLENGE. THEN THE NEXT.",
            "line": "Do not negotiate with the backlog. The Commander already made the decision.",
            "rule": "Minimum viable win: one tier, one camo tick, one level, or one honest partial.",
        },
    ],
    "supportive": [
        {
            "headline": "YOU DO NOT NEED TO FINISH BO7 TONIGHT.",
            "line": "You only need to make the tracker smaller than it was before you queued.",
            "rule": "Start with one stop. If the game feels awful after that, bank the partial and leave clean.",
        },
        {
            "headline": "JUST ONE MORE CHALLENGE.",
            "line": "This is not a motivation test. This is a tiny progress test.",
            "rule": "Play for proof, not perfection. A partial is still useful data.",
        },
    ],
    "spite": [
        {
            "headline": "THE GAME WANTS YOU TO QUIT. DO NOT GIVE IT THAT WIN.",
            "line": "The ugly challenges count the same as the fun ones when the tracker moves.",
            "rule": "Make one annoying item less annoying, then stop before frustration owns the session.",
        },
        {
            "headline": "BANK THE UGLY PROGRESS.",
            "line": "This is where completion actually happens: bad tasks, low patience, one small win.",
            "rule": "No reroll because it is boring. Reroll only if it is impossible or bugged.",
        },
    ],
}


def stable_index(value: str, length: int) -> int:
    if length <= 0:
        return 0

    return sum(ord(char) for char in clean(value)) % length


def morale_tone_for_plan(plan: dict, energy: str, focus: str, days_remaining: int) -> str:
    quick_mode = clean(plan.get("quick_mode_label"))
    commander_mode = clean(plan.get("commander_mode"))
    first = first_stop(plan)
    task_type = clean(first.get("task_type"))

    if "Low" in energy:
        if task_type in {"mastery_badge_equipment", "calling_card", "dark_ops"}:
            return "spite"
        return "supportive"

    if days_remaining <= 30:
        return "drill"

    if quick_mode == "Tracker Cleanup" or commander_mode == "Closest finishes":
        return "spite"

    if focus in {"equipment mastery", "calling cards", "dark ops", "challenges"}:
        return "spite"

    return "drill"


def build_morale_context(plan: dict, energy: str, focus: str, days_remaining: int) -> dict:
    tone = morale_tone_for_plan(plan, energy, focus, days_remaining)
    options = MORALE_BANK.get(tone, MORALE_BANK["supportive"])
    first = first_stop(plan)
    seed = "|".join(
        [
            clean(plan.get("quick_button_label")),
            clean(plan.get("mode")),
            clean(energy),
            clean(first.get("task_id")),
            clean(first.get("weapon")),
            clean(first.get("camo")),
        ]
    )
    chosen = dict(options[stable_index(seed, len(options))])

    weapon = clean(first.get("weapon")) or "the assigned objective"
    camo = clean(first.get("camo")) or "the target"

    chosen.update(
        {
            "tone": tone,
            "micro_action": f"Load in, play the first stop, and look only for proof on {weapon} - {camo}.",
            "fail_safe": "If frustration spikes, log partial progress instead of deleting the session.",
        }
    )

    return chosen


def build_series_context(
    plan: dict,
    task_summary: dict | None = None,
    completion_state: dict | None = None,
    target: dict | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    target = normalise_target(target, today)
    deadline = target["deadline_date"]
    days_remaining = days_until(deadline, today)

    stops = plan.get("stops", []) or []
    mode = clean(plan.get("mode")) or clean(plan.get("quick_mode_label")) or "Commander choice"
    energy = clean(plan.get("quick_energy_label")) or "Manual"
    focus = dominant_task_type(plan)
    first = first_stop_label(plan)

    hook = hook_for_plan(plan, mode, energy, focus)
    title = episode_title_for_plan(plan, mode, energy, focus)

    proof_points = [
        "Show Commander decision before queueing.",
        "Show the assigned loadout and natural weapon goal.",
        "Capture unlock, progress bar, level gain, camo pop, or challenge tier proof.",
        "End on Mission Control debrief so the route has a verdict.",
    ]

    if stops:
        proof_points.insert(2, f"First proof target: {first}.")

    morale = build_morale_context(plan, energy, focus, days_remaining)

    return {
        "series_name": target["series_name"],
        "deadline_date": deadline,
        "deadline_label": target["deadline_label"],
        "days_remaining": days_remaining,
        "pressure": pressure_label(days_remaining),
        "episode_title": title,
        "thumbnail_text": thumbnail_text_for_plan(mode, energy),
        "hook": hook,
        "stakes": (
            f"{days_remaining} day(s) to the {target['deadline_label']}."
            if days_remaining > 0
            else f"{target['deadline_label']} is live. Every session needs proof."
        ),
        "completion_angle": f"Primary completion angle: {focus}.",
        "route_promise": (
            f"Commander selected {len(stops)} stop(s) in {mode}. "
            f"First target: {first}."
        ),
        "pace_line": completion_progress_line(task_summary, completion_state),
        "intro_line": f"Today I am not choosing the grind. The Commander picked {mode}, and I have to follow it.",
        "mid_session_line": "No rerolls unless the objective is impossible. If it fails, the debrief blames the route.",
        "outro_line": "The AI chose the grind. The tracker decides if it was worth it.",
        "proof_points": proof_points,
        "morale": morale,
        "morale_headline": morale.get("headline", ""),
        "morale_line": morale.get("line", ""),
        "morale_rule": morale.get("rule", ""),
        "morale_micro_action": morale.get("micro_action", ""),
        "morale_fail_safe": morale.get("fail_safe", ""),
        "morale_tone": morale.get("tone", ""),
    }


def attach_series_context_to_plan(
    plan: dict,
    task_summary: dict | None = None,
    completion_state: dict | None = None,
    target: dict | None = None,
) -> dict:
    updated = dict(plan or {})
    updated["series_context"] = build_series_context(
        updated,
        task_summary=task_summary,
        completion_state=completion_state,
        target=target,
    )
    updated["series_director_source"] = "series_director_v1"
    return updated


def series_recording_lines_for_plan(plan: dict) -> str:
    context = plan.get("series_context", {}) if isinstance(plan, dict) else {}

    if not context:
        context = build_series_context(plan or {})

    proof_points = context.get("proof_points", []) or []
    proof_text = "\n".join(f"PROOF {index + 1}: {point}" for index, point in enumerate(proof_points))

    return "\n".join(
        [
            f"TITLE: {context.get('episode_title', 'AI Chose My BO7 Grind')}",
            f"HOOK: {context.get('hook', '')}",
            f"STAKES: {context.get('stakes', '')}",
            f"MORALE: {context.get('morale_headline', '')} {context.get('morale_line', '')}",
            f"ANGLE: {context.get('completion_angle', '')}",
            f"ROUTE: {context.get('route_promise', '')}",
            "RULE: No rerolls unless the objective is impossible.",
            "",
            proof_text,
            "",
            f"INTRO: {context.get('intro_line', '')}",
            f"MID: {context.get('mid_session_line', '')}",
            f"OUTRO: {context.get('outro_line', '')}",
        ]
    ).strip()

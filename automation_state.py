import json
from datetime import date

import config


def _default_state() -> dict:
    return {
        "next_tirz_date": None,
        "pending_tirz_prompt_for": None,
        "last_daily_sync_date": None,
        "last_appetite_prompt_date": None,
        "last_weight_prompt_date": None,
        "last_training_prompt_date": None,
        "last_pool_prompt_date": None,
        "last_zone_coloring_date": None,
        "last_weekly_pdf_week": None,
        "pending_text_prompts": [],
    }


def load_state() -> dict:
    if not config.AUTOMATION_STATE_FILE.exists():
        return _default_state()

    with open(config.AUTOMATION_STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    base = _default_state()
    base.update(state)
    return base


def save_state(state: dict):
    config.AUTOMATION_STATE_FILE.parent.mkdir(exist_ok=True)
    with open(config.AUTOMATION_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def ensure_initialized(state: dict) -> dict:
    settings = config.load_settings()
    start_date = settings.get("start_date")
    if start_date and not state.get("next_tirz_date"):
        state["next_tirz_date"] = start_date
    return state


def add_pending_text_prompt(
    state: dict,
    *,
    kind: str,
    target_date: date,
    message_id: int | None,
) -> dict:
    prompts = state.setdefault("pending_text_prompts", [])
    prompts.append(
        {
            "kind": kind,
            "target_date": target_date.isoformat(),
            "message_id": message_id,
        }
    )
    return state


def pop_pending_text_prompt(state: dict, reply_to_message_id: int | None = None) -> dict | None:
    prompts = state.get("pending_text_prompts", [])
    if not prompts:
        return None

    if reply_to_message_id is not None:
        for index in range(len(prompts) - 1, -1, -1):
            if prompts[index].get("message_id") == reply_to_message_id:
                return prompts.pop(index)

    return prompts.pop()

"""Prepare an overlapping daily intake; review and publication stay separate."""
import argparse
import calendar
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = ROOT / "work/collection/daily-state.json"
TIMEZONE = ZoneInfo("Asia/Shanghai")


def six_months_before(today):
    month_index = today.year * 12 + today.month - 1 - 6
    year, month = divmod(month_index, 12)
    month += 1
    return date(year, month, min(today.day, calendar.monthrange(year, month)[1]))


def plan_window(today, state):
    checkpoints = {}
    for key in ("lastCompleted", "lastBackfill"):
        value = state.get(key)
        checkpoints[key] = date.fromisoformat(value) if value else None
        if checkpoints[key] and checkpoints[key] > today:
            raise ValueError(f"{key} 晚于今天，请核对检查点")
    last_completed, last_backfill = checkpoints["lastCompleted"], checkpoints["lastBackfill"]
    if last_backfill and (not last_completed or last_backfill > last_completed):
        raise ValueError("回查检查点不能晚于最后完成日期")
    backfill = not last_backfill or (today - last_backfill).days >= 7
    if backfill:
        since = six_months_before(today)
        # Catch up a long interruption even if it started outside six months.
        if last_completed:
            since = min(since, last_completed - timedelta(days=3))
    else:
        since = min(today - timedelta(days=7), last_completed - timedelta(days=3))
    return {
        "mode": "backfill" if backfill else "incremental",
        "timezone": "Asia/Shanghai",
        "since": since.isoformat(),
        "until": today.isoformat(),
        "previousCheckpoint": state,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--dry-run", action="store_true", help="Preview without fetching or writing")
    args = cli.parse_args()
    try:
        state = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
        plan = plan_window(datetime.now(TIMEZONE).date(), state)
    except (ValueError, TypeError, AttributeError) as error:
        cli.error(f"每日检索检查点无效：{error}")
    if args.dry_run:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now(TIMEZONE).strftime("%Y-%m-%d/%H%M%S-%f")
    run_dir = ROOT / "work/collection/daily" / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    output = run_dir / "candidates.json"
    plan["output"] = str(output.relative_to(ROOT))
    plan["runDirectory"] = str(run_dir.relative_to(ROOT))
    plan_text = json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    (run_dir / "plan.json").write_text(plan_text)
    (ROOT / "work/collection/daily-plan.json").write_text(plan_text)
    print(plan_text, flush=True)
    result = subprocess.run([
        sys.executable, str(ROOT / "scripts/collect.py"),
        "--since", plan["since"], "--until", plan["until"],
        "--output", str(output), "--refresh",
    ], cwd=ROOT)
    if result.returncode:
        print("采集未完整完成；保留已有目录和检查点，下次继续补查。", file=sys.stderr)
    else:
        print("候选已保存；请按 research/DAILY_UPDATE.md 核验、发布并记录检查点。")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())

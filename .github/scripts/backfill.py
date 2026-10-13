
import os
import re
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
MARKER_FILE = Path("streak-backfill/README.md")
MAX_DAYS = 7


def fail(message):
    raise SystemExit(f"ERROR: {message}")


def parse_date(value, label):
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        fail(f"{label} must use YYYY-MM-DD format.")

    if parsed.isoformat() != value:
        fail(f"{label} must use YYYY-MM-DD format.")

    return parsed


def run_git(*args, env=None):
    subprocess.run(
        ["git", *args],
        check=True,
        env=env,
    )


if os.getenv("CONFIRM_BACKFILL", "").lower() != "true":
    fail("Confirmation is required.")

start = parse_date(os.getenv("START_DATE", ""), "Start date")
end = parse_date(os.getenv("END_DATE", ""), "End date")
email = os.getenv("AUTHOR_EMAIL", "").strip()
actor = os.getenv("GITHUB_ACTOR_NAME", "GitHub user")

if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
    fail("Enter a valid email linked to your GitHub account.")

today = datetime.now(IST).date()

if start > end:
    fail("Start date must be on or before end date.")

if end >= today:
    fail("Only dates before today (India time) are allowed.")

if (end - start).days + 1 > MAX_DAYS:
    fail("Select no more than 7 calendar days per run.")

# Ensure this is a Git repository on its default branch.
branch = subprocess.check_output(
    ["git", "branch", "--show-current"], text=True
).strip()

default_branch = os.getenv("GITHUB_REF_NAME", "")

if branch != default_branch:
    fail("Run this workflow on the repository's default branch.")

MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)

if not MARKER_FILE.exists():
    MARKER_FILE.write_text(
        "# Generated backfill records\n\n"
        "These entries are generated records, not evidence "
        "of work performed on the listed dates.\n\n",
        encoding="utf-8",
    )

existing = MARKER_FILE.read_text(encoding="utf-8")
created = 0
skipped = 0

for offset in range((end - start).days + 1):
    day = start + timedelta(days=offset)
    marker = f"- {day.isoformat()}: generated backfill record"

    if marker in existing:
        print(f"SKIP {day}: record already exists.")
        skipped += 1
        continue

    with MARKER_FILE.open("a", encoding="utf-8") as file:
        file.write(marker + "\n")

    run_git("add", str(MARKER_FILE))

    env = os.environ.copy()
    author_time = datetime.combine(
        day, time(12, 0), tzinfo=IST
    ).isoformat()

    env["GIT_AUTHOR_NAME"] = actor
    env["GIT_AUTHOR_EMAIL"] = email
    env["GIT_AUTHOR_DATE"] = author_time

    # Keep the committer timestamp current.
    env.pop("GIT_COMMITTER_DATE", None)
    env["GIT_COMMITTER_NAME"] = actor
    env["GIT_COMMITTER_EMAIL"] = email

    run_git(
        "commit",
        "-m",
        f"chore(backfill): labelled record for {day.isoformat()}",
        env=env,
    )

    existing += marker + "\n"
    created += 1
    print(f"CREATED {day}: labelled record.")

print(f"Finished. Created: {created}; skipped: {skipped}.")

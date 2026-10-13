
import os
import re
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
MARKER_FILE = Path("streak-backfill/README.md")
MAX_DAYS = 7
MAX_COMMITS_PER_DAY = 5


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
    subprocess.run(["git", *args], check=True, env=env)


def read_records():
    if not MARKER_FILE.exists():
        return ""

    return MARKER_FILE.read_text(encoding="utf-8")


def existing_entry_numbers(content, target_date):
    """Find existing entries for a date, including the older format."""
    pattern = re.compile(
        rf"^- {re.escape(target_date)}: generated backfill record"
        rf"(?: \(entry (\d+) of \d+\))?$",
        re.MULTILINE,
    )

    numbers = set()

    for match in pattern.finditer(content):
        # Older version used one unnumbered record per date.
        number = int(match.group(1)) if match.group(1) else 1
        numbers.add(number)

    return numbers


def main():
    if os.getenv("CONFIRM_BACKFILL", "").lower() != "true":
        fail("Confirmation is required.")

    start = parse_date(os.getenv("START_DATE", ""), "Start date")
    end = parse_date(os.getenv("END_DATE", ""), "End date")
    email = os.getenv("AUTHOR_EMAIL", "").strip()
    actor = os.getenv("GITHUB_ACTOR_NAME", "GitHub user")
    default_branch = os.getenv("DEFAULT_BRANCH", "")

    try:
        commits_per_day = int(os.getenv("COMMITS_PER_DAY", "1"))
    except ValueError:
        fail("Commits per day must be a whole number from 1 to 5.")

    if not 1 <= commits_per_day <= MAX_COMMITS_PER_DAY:
        fail("Commits per day must be between 1 and 5.")

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        fail("Enter a valid email associated with your GitHub account.")

    today = datetime.now(IST).date()

    if start > end:
        fail("Start date must be on or before end date.")

    if end >= today:
        fail("Only dates before today in India time are allowed.")

    total_days = (end - start).days + 1

    if total_days > MAX_DAYS:
        fail("Select no more than 7 calendar days per run.")

    branch = subprocess.check_output(
        ["git", "branch", "--show-current"],
        text=True,
    ).strip()

    if not default_branch or branch != default_branch:
        fail("Checkout is not on the repository's default branch.")

    MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)

    if not MARKER_FILE.exists():
        MARKER_FILE.write_text(
            "# Generated backfill records\n\n"
            "These are generated records, not evidence of work "
            "performed on the listed dates.\n\n",
            encoding="utf-8",
        )

    created = 0
    skipped = 0

    for offset in range(total_days):
        day = start + timedelta(days=offset)
        day_text = day.isoformat()

        content = read_records()
        existing = existing_entry_numbers(content, day_text)

        for entry_number in range(1, commits_per_day + 1):
            if entry_number in existing:
                skipped += 1
                continue

            marker = (
                f"- {day_text}: generated backfill record "
                f"(entry {entry_number} of {commits_per_day})"
            )

            with MARKER_FILE.open("a", encoding="utf-8") as file:
                file.write(marker + "\n")

            run_git("add", str(MARKER_FILE))

            # Set the author date to the selected past date.
            # Keep the committer date at the actual execution time.
            author_time = datetime.combine(
                day,
                time(12, entry_number - 1, tzinfo=IST),
            ).isoformat()

            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = actor
            env["GIT_AUTHOR_EMAIL"] = email
            env["GIT_AUTHOR_DATE"] = author_time

            env["GIT_COMMITTER_NAME"] = "github-actions[bot]"
            env["GIT_COMMITTER_EMAIL"] = (
                "41898282+github-actions[bot]@users.noreply.github.com"
            )
            env.pop("GIT_COMMITTER_DATE", None)

            run_git(
                "commit",
                "-m",
                f"chore(backfill): labelled record for {day_text} "
                f"({entry_number}/{commits_per_day})",
                env=env,
            )

            existing.add(entry_number)
            created += 1

            print(
                f"CREATED {day_text}: "
                f"entry {entry_number}/{commits_per_day}"
            )

        if len(existing) >= commits_per_day:
            print(
                f"CHECKED {day_text}: "
                f"{len(existing)} existing record(s) found."
            )

    print(
        f"Finished. Created {created} commit(s); "
        f"skipped {skipped} existing record(s)."
    )


if __name__ == "__main__":
    main()

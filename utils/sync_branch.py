"""Utility to verify and synchronize the repo with the ai-experiments branch.

Usage (Windows PowerShell / bash):
    python utils/sync_branch.py --branch ai-experiments

Optionally force a clean reset if your working tree is dirty:
    python utils/sync_branch.py --branch ai-experiments --force-reset

The script avoids crashes when git is missing or executed outside a repo and
prints clear next steps for the user. Comments are bilingual (PL/EN).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
from pathlib import Path


logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def run_git_command(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command and return the completed process (no raise)."""

    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)


def ensure_repo(path: Path) -> None:
    """Check if the path is inside a git repo; guide the user if not."""

    result = run_git_command(["rev-parse", "--is-inside-work-tree"], path)
    if result.returncode != 0:
        logging.error(
            "Nie znaleziono repozytorium git w %s (run inside cloned folder).", path
        )
        logging.error(
            "Brak .git — uruchom 'git clone --branch ai-experiments <url>' w katalogu nadrzędnym."
        )
        raise SystemExit(1)


def current_branch(path: Path) -> str:
    result = run_git_command(["branch", "--show-current"], path)
    if result.returncode != 0:
        logging.error("Nie mogę odczytać aktualnego branchu (git error).")
        raise SystemExit(1)
    return result.stdout.strip()


def remote_exists(path: Path, remote: str) -> bool:
    result = run_git_command(["remote"], path)
    return result.returncode == 0 and remote in result.stdout.split()


def fetch_remote(path: Path, remote: str) -> None:
    result = run_git_command(["fetch", remote], path)
    if result.returncode != 0:
        logging.error("git fetch %s nie powiódł się: %s", remote, result.stderr.strip())
        raise SystemExit(1)


def rev_parse(path: Path, ref: str) -> str:
    result = run_git_command(["rev-parse", ref], path)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def working_tree_clean(path: Path) -> bool:
    result = run_git_command(["status", "--porcelain"], path)
    return result.returncode == 0 and result.stdout.strip() == ""


def force_reset(path: Path, branch: str, remote: str) -> None:
    """Hard reset + clean + checkout + pull to match remote branch."""

    logging.info("⚠️  Wykonuję reset do %s/%s", remote, branch)
    steps = [
        ["reset", "--hard"],
        ["clean", "-fd"],
        ["checkout", branch],
        ["pull", remote, branch],
    ]
    for step in steps:
        result = run_git_command(step, path)
        if result.returncode != 0:
            logging.error("Polecenie git %s nie powiodło się: %s", " ".join(step), result.stderr)
            raise SystemExit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ensure the repo tracks ai-experiments branch.")
    parser.add_argument("--branch", default="ai-experiments", help="Branch to sync (default: ai-experiments)")
    parser.add_argument("--remote", default="origin", help="Remote name (default: origin)")
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="Hard reset & clean to match remote branch (uwaga: usuwa lokalne zmiany)",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Ścieżka do repo (default: current working dir)",
    )
    args = parser.parse_args()

    if shutil.which("git") is None:
        logging.error("Git nie jest zainstalowany lub nie jest w PATH.")
        raise SystemExit(1)

    repo_path = args.repo
    ensure_repo(repo_path)

    if not remote_exists(repo_path, args.remote):
        logging.error("Remote '%s' nie istnieje — dodaj go: git remote add %s <url>", args.remote, args.remote)
        raise SystemExit(1)

    fetch_remote(repo_path, args.remote)

    local_branch = current_branch(repo_path)
    if local_branch != args.branch:
        logging.warning("Jesteś na branchu %s, oczekiwano %s — przełączam.", local_branch, args.branch)
        checkout = run_git_command(["checkout", args.branch], repo_path)
        if checkout.returncode != 0:
            logging.error("Nie udało się przełączyć na %s: %s", args.branch, checkout.stderr.strip())
            raise SystemExit(1)

    remote_hash = rev_parse(repo_path, f"{args.remote}/{args.branch}")
    local_hash = rev_parse(repo_path, "HEAD")
    logging.info("Local HEAD: %s", local_hash)
    logging.info("Remote %s/%s: %s", args.remote, args.branch, remote_hash)

    clean = working_tree_clean(repo_path)
    if not clean and not args.force_reset:
        logging.warning(
            "Masz lokalne zmiany (git status nie jest czysty). Użyj --force-reset albo zrób kopię/commit."
        )
    if args.force_reset:
        force_reset(repo_path, args.branch, args.remote)
        logging.info("Repo zsynchronizowane z %s/%s.", args.remote, args.branch)
        return

    if local_hash != remote_hash:
        logging.info("Pulling latest changes…")
        pull = run_git_command(["pull", args.remote, args.branch], repo_path)
        if pull.returncode != 0:
            logging.error("git pull nie powiódł się: %s", pull.stderr.strip())
            raise SystemExit(1)
    else:
        logging.info("Repo już jest aktualne.")

    logging.info("✅ Gotowe. Uruchom: python app.py (w tym folderze)")


if __name__ == "__main__":
    main()

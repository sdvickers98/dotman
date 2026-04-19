#!/usr/bin/env python3
"""
Dotfile Manager — backs up dotfiles from ~/.config (or a custom directory).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONFIG_FILE = Path.home() / ".dotfile_manager.json"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_config(data: dict) -> None:
    existing = load_config()
    existing.update(data)
    CONFIG_FILE.write_text(json.dumps(existing, indent=2))


def resolve_filter(
    include: list[str] | None,
    exclude: list[str] | None,
) -> tuple[list[str] | None, list[str] | None]:
    """
    If the user passed a filter on the CLI, save it and return it.
    If not, check for a saved filter and prompt the user to confirm it.
    Returns (include, exclude).
    """
    cfg = load_config()

    if include or exclude:
        # User supplied a new filter — save it
        save_config({
            "filter_type": "include" if include else "exclude",
            "filter_dirs": include or exclude,
        })
        return include, exclude

    saved_type = cfg.get("filter_type")
    saved_dirs = cfg.get("filter_dirs")

    if saved_type and saved_dirs:
        dirs_str = ", ".join(saved_dirs)
        answer = input(
            f"\nSaved {saved_type} filter found: [{dirs_str}]\n"
            f"Use this filter for the current backup? [Y/n] "
        ).strip().lower()
        if answer in ("", "y", "yes"):
            if saved_type == "include":
                return saved_dirs, None
            else:
                return None, saved_dirs
        else:
            print("Skipping saved filter — backing up everything.")

    return None, None


def get_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def collect_dotfiles(
    source_dir: Path,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
) -> list[Path]:
    """Recursively collect files under source_dir, applying whitelist or blacklist."""
    if not source_dir.exists():
        print(f"Error: source directory '{source_dir}' does not exist.", file=sys.stderr)
        sys.exit(1)

    if include:
        # Validate that every requested subdir exists
        for name in include:
            if not (source_dir / name).exists():
                print(f"Error: --include '{name}' not found under '{source_dir}'.", file=sys.stderr)
                sys.exit(1)
        files = []
        for name in include:
            subdir = source_dir / name
            files += [p for p in subdir.rglob("*") if p.is_file()]
        return files

    if exclude:
        excluded = {source_dir / name for name in exclude}
        return [
            p for p in source_dir.rglob("*")
            if p.is_file() and not any(p.is_relative_to(ex) for ex in excluded)
        ]

    return [p for p in source_dir.rglob("*") if p.is_file()]


def run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run a git command in cwd, printing output. Exits on failure."""
    result = subprocess.run(["git"] + args, cwd=cwd, text=True, capture_output=True)
    if result.stdout.strip():
        print(result.stdout.strip())
    if result.returncode != 0:
        print(f"git error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result


def git_init_repo(backup_dir: Path, remote_url: str) -> None:
    """Initialise a git repo in backup_dir and add the remote if not already set up."""
    git_dir = backup_dir / ".git"
    if not git_dir.exists():
        print(f"\nInitialising git repo in '{backup_dir}'...")
        backup_dir.mkdir(parents=True, exist_ok=True)
        run_git(["init", "-b", "main"], cwd=backup_dir)
        run_git(["remote", "add", "origin", remote_url], cwd=backup_dir)
    else:
        # Update remote URL in case it changed
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=backup_dir, text=True, capture_output=True,
        )
        if result.returncode != 0:
            run_git(["remote", "add", "origin", remote_url], cwd=backup_dir)
        elif result.stdout.strip() != remote_url:
            run_git(["remote", "set-url", "origin", remote_url], cwd=backup_dir)


def git_commit_and_push(backup_dir: Path, timestamp: str) -> None:
    """Stage all changes, commit, and push to origin/main."""
    print("\nPushing to remote...")
    run_git(["add", "--all"], cwd=backup_dir)

    # Check if there's anything to commit
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=backup_dir, text=True, capture_output=True,
    )
    if not status.stdout.strip():
        print("Nothing new to commit — remote is already up to date.")
        return

    run_git(["commit", "-m", f"backup: {timestamp}"], cwd=backup_dir)

    # Push; use --set-upstream on first push
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=backup_dir, text=True, capture_output=True,
    )
    if result.returncode != 0:
        # Likely first push — try with --set-upstream
        run_git(["push", "--set-upstream", "origin", "main"], cwd=backup_dir)
    else:
        if result.stdout.strip():
            print(result.stdout.strip())

    print("Remote push complete.")


def backup(
    source_dir: Path,
    backup_dir: Path,
    dry_run: bool = False,
    remote_url: str | None = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    no_save: bool = False,
) -> None:
    if no_save:
        # Use the CLI filter as-is without touching saved config
        resolved_include, resolved_exclude = include, exclude
    else:
        resolved_include, resolved_exclude = resolve_filter(include, exclude)

    files = collect_dotfiles(source_dir, include=resolved_include, exclude=resolved_exclude)

    if not files:
        print(f"No files found in '{source_dir}'.")
        return

    timestamp = get_timestamp()
    dest_root = backup_dir / f"dotfiles_backup_{timestamp}"

    print(f"Source : {source_dir}")
    print(f"Backup : {dest_root}")
    print(f"Files  : {len(files)}")
    if resolved_include:
        print(f"Include: {', '.join(resolved_include)}")
    if resolved_exclude:
        print(f"Exclude: {', '.join(resolved_exclude)}")
    if remote_url:
        print(f"Remote : {remote_url}")
    if dry_run:
        print("\n[dry-run] No files will be copied.\n")

    for src in files:
        # Preserve directory structure relative to source_dir
        relative = src.relative_to(source_dir)
        dest = dest_root / relative

        if dry_run:
            print(f"  would copy: {relative}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  copied: {relative}")

    if not dry_run:
        print(f"\nBackup complete → {dest_root}")
        if remote_url:
            git_init_repo(backup_dir, remote_url)
            git_commit_and_push(backup_dir, timestamp)


def restore(backup_path: Path, target_dir: Path, dry_run: bool = False) -> None:
    if not backup_path.exists():
        print(f"Error: backup path '{backup_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    files = [p for p in backup_path.rglob("*") if p.is_file()]

    if not files:
        print(f"No files found in backup '{backup_path}'.")
        return

    print(f"Restoring from : {backup_path}")
    print(f"Target         : {target_dir}")
    print(f"Files          : {len(files)}")
    if dry_run:
        print("\n[dry-run] No files will be restored.\n")

    for src in files:
        relative = src.relative_to(backup_path)
        dest = target_dir / relative

        if dry_run:
            print(f"  would restore: {relative}")
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            print(f"  restored: {relative}")

    if not dry_run:
        print(f"\nRestore complete → {target_dir}")


def list_backups(backup_dir: Path) -> None:
    if not backup_dir.exists():
        print(f"No backups found (directory '{backup_dir}' does not exist).")
        return

    backups = sorted(
        [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith("dotfiles_backup_")],
        reverse=True,
    )

    if not backups:
        print(f"No backups found in '{backup_dir}'.")
        return

    print(f"Backups in '{backup_dir}':\n")
    for b in backups:
        file_count = sum(1 for _ in b.rglob("*") if _.is_file())
        print(f"  {b.name}  ({file_count} files)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dotfile Manager — backup and restore ~/.config dotfiles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Backup ~/.config to ~/dotfile_backups/
  python dotfile_manager.py backup

  # Backup a custom config directory
  python dotfile_manager.py backup --source ~/my_configs

  # Backup to a custom destination
  python dotfile_manager.py backup --dest /mnt/usb/backups

  # Backup and push to a GitHub repo
  python dotfile_manager.py backup --remote git@github.com:user/dotfiles.git

  # Backup to a custom destination and push remotely
  python dotfile_manager.py backup --dest /mnt/usb/backups --remote git@github.com:user/dotfiles.git

  # Only back up specific subdirectories (whitelist) — saves for future runs
  python dotfile_manager.py backup --include nvim git fish

  # Back up everything except certain subdirectories (blacklist) — saves for future runs
  python dotfile_manager.py backup --exclude chromium BraveSoftware

  # Use a filter for this run only, without saving it
  python dotfile_manager.py backup --include nvim --no-save

  # Clear the saved filter
  python dotfile_manager.py clear-filter

  # List all backups
  python dotfile_manager.py list

  # Restore a specific backup
  python dotfile_manager.py restore ~/dotfile_backups/dotfiles_backup_20260418_120000
        """,
    )

    default_source = Path.home() / ".config"
    default_dest = Path.home() / "dotfile_backups"

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- backup ---
    backup_parser = subparsers.add_parser("backup", help="Create a backup of dotfiles.")
    backup_parser.add_argument(
        "--source", type=Path, default=default_source,
        help=f"Config directory to back up (default: {default_source})",
    )
    backup_parser.add_argument(
        "--dest", type=Path, default=default_dest,
        help=f"Directory to store backups (default: {default_dest})",
    )
    backup_parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be backed up without copying files.",
    )
    backup_parser.add_argument(
        "--remote", metavar="URL",
        help="Git remote URL to push the backup to (e.g. git@github.com:user/dotfiles.git).",
    )
    filter_group = backup_parser.add_mutually_exclusive_group()
    filter_group.add_argument(
        "--include", nargs="+", metavar="DIR",
        help="Only back up these subdirectories of source (whitelist). Cannot be used with --exclude.",
    )
    filter_group.add_argument(
        "--exclude", nargs="+", metavar="DIR",
        help="Skip these subdirectories of source (blacklist). Cannot be used with --include.",
    )
    backup_parser.add_argument(
        "--no-save", action="store_true",
        help="Use the supplied --include/--exclude for this run only; do not save or load from config.",
    )

    # --- clear-filter ---
    subparsers.add_parser("clear-filter", help="Remove the saved include/exclude filter.")

    # --- restore ---
    restore_parser = subparsers.add_parser("restore", help="Restore dotfiles from a backup.")
    restore_parser.add_argument(
        "backup_path", type=Path,
        help="Path to the backup directory to restore from.",
    )
    restore_parser.add_argument(
        "--target", type=Path, default=default_source,
        help=f"Directory to restore files into (default: {default_source})",
    )
    restore_parser.add_argument(
        "--dry-run", action="store_true",
        help="Preview what would be restored without copying files.",
    )

    # --- list ---
    list_parser = subparsers.add_parser("list", help="List available backups.")
    list_parser.add_argument(
        "--dest", type=Path, default=default_dest,
        help=f"Directory where backups are stored (default: {default_dest})",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "backup":
        backup(
            args.source, args.dest,
            dry_run=args.dry_run,
            remote_url=args.remote,
            include=args.include,
            exclude=args.exclude,
            no_save=args.no_save,
        )
    elif args.command == "restore":
        restore(args.backup_path, args.target, dry_run=args.dry_run)
    elif args.command == "list":
        list_backups(args.dest)
    elif args.command == "clear-filter":
        cfg = load_config()
        if "filter_type" not in cfg:
            print("No saved filter to clear.")
        else:
            cfg.pop("filter_type", None)
            cfg.pop("filter_dirs", None)
            CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
            print("Saved filter cleared.")


if __name__ == "__main__":
    main()

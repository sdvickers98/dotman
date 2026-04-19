# Dotfile Manager

A simple CLI tool to back up and restore dotfiles from `~/.config` (or any directory you choose).

## Requirements

Python 3.10+, no external dependencies.

## Usage

### Backup

```bash
# Backup ~/.config → ~/dotfile_backups/dotfiles_backup_<timestamp>/
python dotfile_manager.py backup

# Custom source directory
python dotfile_manager.py backup --source ~/my_configs

# Custom backup destination
python dotfile_manager.py backup --dest /mnt/usb/backups

# Preview without copying
python dotfile_manager.py backup --dry-run
```

### Remote backup (GitHub)

Push your backup to a private GitHub repo for versioned, off-site storage.

**First-time setup:**
1. Create a new private repo on GitHub (no README, no .gitignore — keep it empty).
2. Make sure your SSH key is added to GitHub, or use an HTTPS URL with a token.

```bash
# Backup and push to GitHub via SSH
python dotfile_manager.py backup --remote git@github.com:youruser/dotfiles.git

# Or via HTTPS
python dotfile_manager.py backup --remote https://github.com/youruser/dotfiles.git

# Combine with a custom source or destination
python dotfile_manager.py backup --source ~/my_configs --remote git@github.com:youruser/dotfiles.git
```

On the first run the backup directory is initialised as a git repo and the remote is added automatically. Every subsequent backup commits the new snapshot and pushes it — so you get a full history of every backup in git.

### Filtering (whitelist / blacklist)

These are mutually exclusive — pick one or the other.

```bash
# Only back up specific subdirectories (whitelist) — saved for future runs
python dotfile_manager.py backup --include nvim git fish

# Back up everything except certain subdirectories (blacklist) — saved for future runs
python dotfile_manager.py backup --exclude chromium BraveSoftware

# Combine with other flags
python dotfile_manager.py backup --include nvim git --remote git@github.com:youruser/dotfiles.git
python dotfile_manager.py backup --exclude chromium --dry-run
```

`--include` and `--exclude` accept one or more directory names relative to the source directory. Passing both at the same time is an error.

Filters are saved to `~/.dotfile_manager.json` automatically. On the next backup run where no filter is passed on the CLI, you'll be prompted:

```
Saved exclude filter found: [chromium, BraveSoftware]
Use this filter for the current backup? [Y/n]
```

Press Enter or `y` to use it, `n` to skip it for that run.

```bash
# Use a filter for this run only, without saving or loading from config
python dotfile_manager.py backup --include nvim --no-save

# Remove the saved filter entirely
python dotfile_manager.py clear-filter
```

### List backups

```bash
python dotfile_manager.py list

# Custom backup location
python dotfile_manager.py list --dest /mnt/usb/backups
```

### Restore

```bash
# Restore a specific backup into ~/.config
python dotfile_manager.py restore ~/dotfile_backups/dotfiles_backup_20260418_120000

# Restore into a different directory
python dotfile_manager.py restore ~/dotfile_backups/dotfiles_backup_20260418_120000 --target ~/restored_configs

# Preview without copying
python dotfile_manager.py restore ~/dotfile_backups/dotfiles_backup_20260418_120000 --dry-run
```

## Backup structure

Each backup is a timestamped folder that mirrors the source directory layout:

```
~/dotfile_backups/
└── dotfiles_backup_20260418_120000/
    ├── nvim/
    │   └── init.lua
    ├── git/
    │   └── config
    └── ...
```

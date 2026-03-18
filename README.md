# FED3 Data Aggregation Script

**A Python tool to aggregate and analyze FED3 (FED3 pellet dispenser) experiment data from CSV exports.**

This script processes raw FED3 `.csv` files (one per animal/session), aggregates data into time bins, computes summary statistics (pellets, pokes, etc.), and optionally identifies **breakpoints** in Progressive Ratio (PR) schedules where response rates change significantly.

## Features

- Reads multiple FED3 CSV files from a folder
- Parses animal/condition metadata from filenames (e.g. `Strain_Diet_Cohort_FED999_date.csv`)
- Interactive prompts **or** full CLI mode for session length, bin size, breakpoint FR
- Aggregates data into user-defined time bins (e.g. 5-min, 10-min)
- Computes per-bin and session totals: pellets, left/right pokes, retrieval times, active/inactive FR
- Breakpoint analysis — detects shifts in FR using a user-provided threshold
- Test mode with sample data for quick development/debugging
- Outputs clean CSV summaries in a tidy format (per-animal and group-level)

## Quick Start

### Option 1: Download & Run the Standalone .exe (Windows – no Python needed)

1. Go to [Releases](https://github.com/brbarnhart/Fed3_Data_Aggregation_Script/releases) (or build your own – see below)
2. Download the latest `fed3-aggregate.exe`
3. Place your FED3 `.csv` files in a folder called `raw_data` next to the .exe (or any folder)
    Naming scheme for `.csv` files: 
    "field1_field2_field3_etc.csv"

    Replace each field with the appropriate level for that file
    Example:
    "ID_Sex_Cage_Stimulation_Diet.csv"

4. Double-click the .exe — or open Command Prompt in that folder and run:

  ```cmd
  fed3-aggregate.exe
  ```
Follow the prompts — or use flags for non-interactive runs:
  ```cmd
  fed3-aggregate.exe --data raw_data --session 60 --bin 5 --breakpoint 10
  ```

### Option 2: Run with Python (recommended for developers / Mac/Linux)
Requires Python 3.10+ and uv (fast modern package manager).
  ```Bash
  # 1. Clone or download the repo
  git clone https://github.com/brbarnhart/Fed3_Data_Aggregation_Script.git
  cd Fed3_Data_Aggregation_Script
  
  # 2. Install dependencies (creates .venv automatically)
  uv sync
  
  # 3. Run (interactive mode)
  uv run python main.py
  
  # Or non-interactive / test mode
  uv run python main.py --test --data sample_data --session 60 --bin 5 --breakpoint 10
  ```

Alternative with plain pip (slower install):
  ```Bash
  pip install -r requirements.txt    # (generate via uv export if needed)
  python main.py
  ```

### CLI Flags (non-interactive mode)
All flags are optional — if omitted, the script prompts interactively.

Flag,Type,Default,Description
--data,str,raw_data,Folder containing .csv files (try sample_data for testing)
--session,int,(prompt),Session length in minutes
--bin,int,(prompt),Bin size in minutes for aggregation
--breakpoint,float,(prompt),FR threshold for breakpoint detection (enables mode if provided)
--test,flag,off,Use defaults for condition names (skips prompts)
--condition-names,strings,(prompt),"Override condition field names, e.g. --condition-names Strain Diet Cohort"

Examples:
  ```Bash
  # Test with sample data + breakpoint analysis
  python main.py --test --data sample_data --session 120 --bin 10 --breakpoint 8.5
  
  # Real data, fully non-interactive
  python main.py --data my_experiment --session 180 --bin 15 --breakpoint 12
  ```

### Folder Structure
 - raw_data/ — place your real FED3 .csv exports here (default input)
 - sample_data/ — tiny example files for testing / debugging (included)
 - clean_data/ — (optional) where aggregated output CSVs are saved
 - main.py — the main script
 - pyproject.toml + uv.lock — modern dependency & packaging config
 - .zed/ — Zed editor debug configs (optional for developers)

### How to Build a Standalone .exe (Windows)
If you want to distribute an executable:

  ```Bash
  uv pip install pyinstaller
  pyinstaller --onefile --name fed3-aggregate --console main.py
  ```
  
The .exe appears in dist/. Test it and upload to GitHub Releases.

### Development / Testing Tips
 - Use --test for fast runs (skips condition name prompts)
 - Zed users: See .zed/debug.json for debugger configs with flags
 - Add breakpoints in main.py (e.g. in aggregation or breakpoint logic)
 - Sample data includes short sessions with pellets and pokes for breakpoint testing

### Output Files
The script generates CSV(s) with columns like:

 - Timestamp bins
 - Pellets, Left/Right Pokes, Retrieval Time
 - Active/Inactive FR
 - Cumulative values
 - Breakpoint indicators (if enabled)

Check clean_data/ or console for paths.

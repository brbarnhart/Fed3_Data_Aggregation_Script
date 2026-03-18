import argparse
import warnings
from pathlib import Path

import pandas as pd
import questionary

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


def get_raw_data_files(raw_data_path: Path) -> list[Path]:
    files = list(raw_data_path.glob("*.csv"))  # or "**/*.csv" if recursive, etc.

    if not files:
        raise ValueError(
            f"No FED3 CSV files found in '{raw_data_path}'.\n"
            "Please make sure:\n"
            "  - The folder contains at least one file ending in .csv\n"
            "  - The files follow the expected FED3 naming format (e.g. containing '_FED' or similar)\n"
            "  - You're using the correct --data flag if not using the default 'raw_data' folder\n\n"
            "Example: Place your data files in ./raw_data/ or run with --data sample_data for testing."
        )

    return files


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="fed3 data aggregation script",
        epilog="run without flags for interactive mode (real data). use flags for testing / automation.",
    )
    parser.add_argument(
        "--data",
        default="raw_data",
        help="folder to read data from (default: raw_data, or use 'sample_data' for testing)",
    )
    parser.add_argument(
        "--session",
        type=int,
        default=None,
        help="session length in minutes (skips prompt if provided)",
    )
    parser.add_argument(
        "--bin",
        type=int,
        default=None,
        help="bin size in minutes for aggregation (skips prompt if provided)",
    )
    parser.add_argument(
        "--breakpoint",
        type=int,
        default=None,
        help="inactive time threshold in minutes for breakpoint mode (if provided, enables breakpoint mode and skips prompt)",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="run in test mode: skip all prompts and use defaults",
    )

    return parser


def ask_positive_integer(message: str) -> int:
    """prompt for a positive integer with validation."""
    response = questionary.text(
        message=message,
        validate=lambda val: (
            True
            if val.strip().isdigit() and int(val) > 0
            else "invalid input. please enter a positive integer."
        ),
    ).ask()
    return int(response)


def get_user_inputs(args) -> tuple[int, int, int]:

    # check for test mode
    if args.test:
        print("running in test mode: using default values")
        session_length_min = 90
        bin_size = 30
        breakpoint_time = 15
        return (session_length_min, bin_size, breakpoint_time)

    # interactive inputs
    if args.session is not None:
        session_length_min = args.session
        print(f"using session length from cli: {session_length_min} minutes")
    else:
        session_length_min = ask_positive_integer(
            "please enter length of feeding session (in minutes): "
        )

    if args.bin is not None:
        bin_size = args.bin
        print(f"using bin size from cli: {bin_size} minutes")
    else:
        bin_size = ask_positive_integer(
            "please enter length of each bin (in minutes): "
        )

    if args.breakpoint is not None:
        breakpoint_time = args.breakpoint
        print(f"using breakpoint time from cli: {breakpoint_time} minutes")
    else:
        breakpoint_time = ask_positive_integer(
            "please enter inactive time for breakpoint (in minutes): "
        )
    return (session_length_min, bin_size, breakpoint_time)


def get_subject_metadata(file_path: Path, num_fields: int = 3) -> str:
    file_name = file_path.stem
    file_fields = file_name.split("_")

    if len(file_fields) <= num_fields:
        print(f"file does not have correct number of fields \n{file_name}")

    return file_name


def get_experiment_condition_names(
    subject_metadata: str,
    test_mode: bool = False,
    default_names: list[str] | None = None,
) -> list[str]:

    example_conditions = subject_metadata.split("_")

    print(f"example conditions: {subject_metadata}")

    if test_mode:
        if default_names is not None and len(default_names) == len(example_conditions):
            field_names = default_names
        else:
            # sensible auto-generated defaults (you can customize these!)
            field_names = [f"cond{i + 1}" for i in range(len(example_conditions))]
            # alternative ideas (pick one):
            # field_names = ["group", "diet", "sex", "cohort"][:len(example_conditions)]
            # field_names = [f"field_{i+1}" for i in range(len(example_conditions))]

        print(f"test mode: using default condition names → {field_names}")
        return field_names

    questions = []
    n = 0
    for field in example_conditions:
        questions.append(
            {"type": "text", "name": str(n), "message": f"name for '{field}' field"}
        )
        n += 1

    field_names = list(questionary.prompt(questions).values())

    return field_names


def read_data(folder_path, file, session_length):
    file_path = folder_path / file

    # read data
    df = pd.read_csv(file_path)
    # print(f"processing file: {file}, shape: {df.shape}, columns: {df.columns}")
    df = df.rename(columns={"MM:DD:YYYY hh:mm:ss": "date"})

    # create a time column to filter by
    df["date"] = pd.to_datetime(df["date"])
    start_time = df["date"].iloc[0]
    df["time"] = df["date"] - start_time
    df = df.set_index("time")

    # only take entries within the designated session length
    df = df.loc[: pd.Timedelta(minutes=session_length)]

    df.index = df.index.total_seconds() / 60
    df = df.sort_index()

    # Calculate active poke intervals
    active_poke = df["Active_Poke"].iloc[0]
    temp_df = df[df["Event"].isin([active_poke, active_poke + "DuringDispense"])]
    temp_df["active_poke_interval"] = temp_df.index.diff()
    df = df.join(temp_df["active_poke_interval"])

    # Calculate intervals for all pokes
    temp_df = df[
        df["Event"].isin(["Left", "LeftDuringDispense", "Right", "RightDuringDispense"])
    ]
    temp_df["any_poke_interval"] = temp_df.index.diff()
    df = df.join(temp_df["any_poke_interval"])

    return df


def get_aggregate_data(df, breakpoint_cutoff):
    last_row = df.iloc[-1]

    # Breakpoint defined as the FR of the last pellet retrieved before the first poke interval (either active or all)
    # exceeds the cutoff or the last pellet retrieved if no poke interval exceeds the cutoff

    # Calculate breakpoint based on active pokes only
    # Find first active poke where interval exceeds breakpoint cutoff
    # Then find the FR of the previous pellet retrieved.
    breaks = df[df["active_poke_interval"] >= breakpoint_cutoff]
    if breaks.shape[0] == 0:
        breakpoint_active_pokes = df[df["Event"] == "Pellet"]["FR"].iloc[-1]
    else:
        break_time = breaks.index[0]
        previous_pellet = df[(df["Event"] == "Pellet") & (df.index < break_time)]
        breakpoint_active_pokes = previous_pellet["FR"].iloc[-1]

    # Calculate breakpoint based on all pokes
    # Find first poke where interval exceeds breakpoint cutoff
    # Then find the FR of the previous pellet retrieved.
    breaks_all = df[df["any_poke_interval"] >= breakpoint_cutoff]
    if breaks_all.shape[0] == 0:
        breakpoint_all_pokes = df[df["Event"] == "Pellet"]["FR"].iloc[-1]
    else:
        break_time_all = breaks_all.index[0]
        previous_pellet_all = df[
            (df["Event"] == "Pellet") & (df.index < break_time_all)
        ]
        breakpoint_all_pokes = previous_pellet_all["FR"].iloc[-1]

    # pull out aggregated data
    aggregate_data = {
        "total_correct_pokes": last_row.get("left_poke_count", 0),
        "total_incorrect_pokes": last_row.get("right_poke_count", 0),
        "total_pellets": last_row.get("pellet_count", 0),
        "breakpoint_active_pokes": breakpoint_active_pokes,
        "breakpoint_all_pokes": breakpoint_all_pokes,
    }
    return aggregate_data


def get_binned_data(df, time_bins):
    # pull out binned data
    columns = ["left_poke_count", "right_poke_count", "pellet_count"]
    binned_data = pd.DataFrame(columns=columns)
    binned_data.loc[0] = 0
    previous_bin_data = None

    for i in range(len(time_bins) - 1):
        time_bin = time_bins[i + 1]
        time_slice = slice(time_bins[i], time_bins[i + 1])
        bin = df.loc[time_slice]

        try:
            bin_data = bin.iloc[-1]
            binned_data.loc[time_bin] = bin_data
            previous_bin_data = bin_data

        except IndexError:
            # assumes there were no entries in this time bin
            bin_data = previous_bin_data
            binned_data.loc[time_bin] = bin_data
            previous_bin_data = bin_data

    # pulling out data to be entered into metric specific dataframes
    subj_data = {
        "binned_correct_pokes": binned_data["left_poke_count"],
        "binned_incorrect_pokes": binned_data["right_poke_count"],
        "binned_pellets": binned_data["pellet_count"],
    }

    return subj_data


def create_df(
    data_files,
    folder_path,
    session_length,
    time_bins,
    breakpoint_cutoff,
    condition_names,
):
    columns = condition_names + [
        "total_correct_pokes",
        "total_incorrect_pokes",
        "total_pellets",
        "binned_correct_pokes",
        "binned_incorrect_pokes",
        "binned_pellets",
        "bin",
        "bin_time",
    ]

    data = pd.DataFrame(columns=columns)
    for file in data_files:
        # parse metadata from file name
        base_name = Path(file).stem
        parts = base_name.split("_")

        if len(parts) != len(condition_names):
            print(f"error parsing metadata from filename: {base_name}")
            print(f"expected fields to be: {condition_names}")
            print(
                f"Length of parts: {len(parts)}, length of condition_names: {len(condition_names)}"
            )
            print(f"parts: {parts}")
            exit()

        df = read_data(folder_path, file, session_length)

        num_bins = len(time_bins)

        subject_info = {k: [v] * num_bins for k, v in zip(condition_names, parts)}
        aggregate_data = get_aggregate_data(df, breakpoint_cutoff)
        aggregate_data = {k: [v] * num_bins for k, v in aggregate_data.items()}
        binned_data = get_binned_data(df, time_bins)

        mouse = {
            **subject_info,
            **aggregate_data,
            **binned_data,
            "bin": list(range(1, num_bins + 1)),
            "bin_time": time_bins,
        }

        data = pd.concat([data, pd.DataFrame(mouse)], ignore_index=True)

    return data


def save_aggregated_data(df, folder_path):
    """
    saves the aggregated dataframes to a csv file.
    """
    script_dir = folder_path.parent
    experiment_name = script_dir.name
    save_dir = script_dir / "clean_data"
    save_dir.mkdir(parents=True, exist_ok=True)

    # save to single excel file
    file_name = save_dir / f"{experiment_name} - data.csv"
    df.to_csv(file_name, index=False)


if __name__ == "__main__":
    cwd = Path(__file__).parent.resolve()

    parser = setup_parser()
    args = parser.parse_args()

    if args.test:
        raw_data_path = (cwd / "sample_data").resolve()
    else:
        raw_data_path = (cwd / args.data).resolve()

    (session_length_min, bin_size, breakpoint_time) = get_user_inputs(args)

    data_files = get_raw_data_files(raw_data_path)

    time_bins = list(range(0, session_length_min + bin_size, bin_size))

    condition_names = get_experiment_condition_names(
        get_subject_metadata(data_files[0]),
        test_mode=args.test,
        default_names=[
            "ID",
            "Sex",
            "Cage",
            "Stim",
            "Diet",
            "Cohort",
            "FeederID",
            "Date",
            "RecordingNumber",
        ],
    )

    df = create_df(
        data_files,
        raw_data_path,
        session_length_min,
        time_bins,
        breakpoint_time,
        condition_names,
    )

    save_aggregated_data(df, raw_data_path)

    print("\nData saved\n")

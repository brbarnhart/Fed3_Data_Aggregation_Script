import os
import warnings
from pathlib import Path

import pandas as pd
import questionary

warnings.filterwarnings("ignore", category=pd.errors.PerformanceWarning)


def get_raw_data_files(raw_data_path: Path) -> list[Path]:
    # grab list of data file names from raw_data folder

    if not raw_data_path.exists():
        print(f"Error: {raw_data_path} does not exist")
        return []
    if not raw_data_path.is_dir():
        print(f"Error: {raw_data_path} is not a directory")
        return []

    data_files = [
        Path(f) for f in os.listdir(raw_data_path) if f.lower().endswith(".csv")
    ]

    if data_files == []:
        print(f"Error: no data files found in {raw_data_path}")

    return data_files


def ask_positive_integer(message: str) -> int:
    """Prompt for a positive integer with validation."""
    response = questionary.text(
        message=message,
        validate=lambda val: (
            True
            if val.strip().isdigit() and int(val) > 0
            else "Invalid input. Please enter a positive integer."
        ),
    ).ask()
    return int(response)


def get_user_inputs() -> tuple[int, int, int]:
    session_length = ask_positive_integer(
        "Please enter length of feeding session (in minutes): "
    )
    bin_size = ask_positive_integer("Please enter length of each bin (in minutes): ")
    breakpoint_time = ask_positive_integer(
        "Please enter inactive time for breakpoint (in minutes): "
    )
    return (session_length, bin_size, breakpoint_time)


def get_subject_metadata(file_path: Path, num_fields: int = 3) -> str:
    file_name = file_path.stem
    file_fields = file_name.split("_")

    if len(file_fields) <= num_fields:
        print(f"File does not have correct number of fields \n{file_name}")

    return file_name


def get_experiment_condition_names(subject_metadata: str) -> list[str]:
    example_conditions = subject_metadata.split("_")

    print(f"Example conditions: {subject_metadata}")

    questions = []
    n = 0
    for field in example_conditions:
        questions.append(
            {"type": "text", "name": str(n), "message": f"Name for '{field}' field"}
        )
        n += 1

    field_names = list(questionary.prompt(questions).values())

    return field_names


def read_data(folder_path, file, session_length):
    file_path = folder_path / file

    # read data
    df = pd.read_csv(file_path)
    # print(f"Processing file: {file}, Shape: {df.shape}, Columns: {df.columns}")
    df = df.rename(columns={"MM:DD:YYYY hh:mm:ss": "date"})

    # Create a time column to filter by
    df["date"] = pd.to_datetime(df["date"])
    start_time = df["date"].iloc[0]
    df["time"] = df["date"] - start_time
    df = df.set_index("time")

    # Only take entries within the designated session length
    df = df.loc[: pd.Timedelta(minutes=session_length)]

    df.index = df.index.total_seconds() / 60
    df = df.sort_index()

    return df


def get_aggregate_data(df):
    last_row = df.iloc[-1]

    # pull out aggregated data
    aggregate_data = {
        "Total_Correct_Pokes": last_row.get("Left_Poke_Count", 0),
        "Total_Incorrect_Pokes": last_row.get("Right_Poke_Count", 0),
        "Total_Pellets": last_row.get("Pellet_Count", 0),
        "Highest_FR": max(df["FR"]),
    }
    return aggregate_data


def get_binned_data(df, time_bins):
    # pull out binned data
    columns = ["Left_Poke_Count", "Right_Poke_Count", "Pellet_Count"]
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
            # Assumes there were no entries in this time bin
            bin_data = previous_bin_data
            binned_data.loc[time_bin] = bin_data
            previous_bin_data = bin_data

    # Pulling out data to be entered into metric specific dataframes
    subj_data = {
        "Binned_Correct_Pokes": binned_data["Left_Poke_Count"],
        "Binned_Incorrect_Pokes": binned_data["Right_Poke_Count"],
        "Binned_Pellets": binned_data["Pellet_Count"],
    }

    return subj_data


def create_df(data_files, folder_path, session_length, time_bins, condition_names):
    columns = condition_names + [
        "Total_Correct_Pokes",
        "Total_Incorrect_Pokes",
        "Total_Pellets",
        "Binned_Correct_Pokes",
        "Binned_Incorrect_Pokes",
        "Binned_Pellets",
        "Bin",
        "Bin_Time",
    ]

    data = pd.DataFrame(columns=columns)
    for file in data_files:
        # parse metadata from file name
        base_name = os.path.splitext(file)[0]
        parts = base_name.split("_")

        if len(parts) != len(condition_names):
            print(f"Error parsing metadata from filename: {base_name}")
            print(f"Expected fields to be: {condition_names}")
            exit()

        df = read_data(folder_path, file, session_length)

        num_bins = len(time_bins)

        subject_info = {k: [v] * num_bins for k, v in zip(condition_names, parts)}
        aggregate_data = get_aggregate_data(df)
        aggregate_data = {k: [v] * num_bins for k, v in aggregate_data.items()}
        binned_data = get_binned_data(df, time_bins)

        mouse = {
            **subject_info,
            **aggregate_data,
            **binned_data,
            "Bin": list(range(1, num_bins + 1)),
            "Bin_Time": time_bins,
        }

        data = pd.concat([data, pd.DataFrame(mouse)], ignore_index=True)

    return data


def save_aggregated_data(df, folder_path):
    """
    Saves the aggregated DataFrames to a csv file.
    """
    script_dir = folder_path.parent
    experiment_name = script_dir.name
    save_dir = script_dir / "clean_data"
    save_dir.mkdir(parents=True, exist_ok=True)

    # Save to single Excel file
    file_name = save_dir / f"{experiment_name} - data.csv"
    df.to_csv(file_name, index=False)


if __name__ == "__main__":
    cwd = Path.cwd()
    raw_data_path = (cwd / "raw_data").resolve()
    data_files = get_raw_data_files(raw_data_path)

    (session_length, bin_size, breakpoint_time) = get_user_inputs()
    time_bins = list(range(0, session_length + bin_size, bin_size))

    condition_names = get_experiment_condition_names(
        get_subject_metadata(data_files[0])
    )

    df = create_df(
        data_files, raw_data_path, session_length, time_bins, condition_names
    )

    save_aggregated_data(df, raw_data_path)

    print("\nData saved\n")

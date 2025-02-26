import subprocess
import os
import shutil
import pandas as pd
import subprocess
import re
import json

paths = {
    'workflow':'./bin/actions_workflow.parquet',
    'jobs':'./bin/actions_jobs.parquet',
    }


class ArqManipulation:
    """
    A utility class for file operations and data manipulation.
    """

    @staticmethod 
    def read_parquet_file(parquet_file_name: str) -> pd.DataFrame:
        """
        Reads a Parquet file and returns a DataFrame.

        :param parquet_file_name: Path to the Parquet file.
        :return: DataFrame with file contents.
        """
        try:
            if not os.path.exists(parquet_file_name):
                return pd.DataFrame()
            
            return pd.read_parquet(parquet_file_name)
        except Exception as e:
            raise RuntimeError(f"Error reading Parquet file '{parquet_file_name}': {e}")

    @staticmethod
    def save_df_to_parquet(df: pd.DataFrame, parquet_file_name: str):
        """
        Saves a DataFrame to a Parquet file.

        :param df: Dataframe to save.
        :param parquet_file_name: Parqueet saving path.
        """
        try:
            os.makedirs(os.path.dirname(parquet_file_name), exist_ok=True)
            df.to_parquet(parquet_file_name)
        except Exception as e:
            raise RuntimeError(f"Error saving DataFrame to Parquet file '{parquet_file_name}': {e}")

    @staticmethod
    def clean_ansi_escape(base_str: str) -> str:
        """
        Removes ANSI escape values from a string.

        :param base_str: Unformmated string.
        :return: Cleaned string.
        """
        return re.sub(r'\x1B\[[0-9;]*[A-Za-z]', '', base_str)

    @staticmethod
    def parse_stdout_json(base_str: str) -> dict:
        """
        Parses JSON output from GitHub CLI after cleaning ANSI escape sequences.

        :param base_str: The raw output string from the GitHub CLI.
        :return: Parsed JSON dictionary.
        """
        try:
            cleaned = ArqManipulation.clean_ansi_escape(base_str)
            str_output = ''.join(cleaned.splitlines())
            return json.loads(str_output)
        except json.JSONDecodeError as e:
            raise e

    @staticmethod
    def json_to_df(parsed_json: dict) -> pd.DataFrame:
        """
        Converts a JSON dictionary to a sorted DataFrame with specific columns.

        :param parsed_json: Parsed JSON data.
        :return: Pandas DataFrame sorted by the 'createdAt' column.
        """
        try:
            df_json = pd.DataFrame(parsed_json)
            required_columns = ['name', 'createdAt', 'conclusion', 'status', 'databaseId', 'workflowDatabaseId']
            
            if not all(col in df_json.columns for col in required_columns):
                raise KeyError(f"Missing required columns in JSON data: {set(required_columns) - set(df_json.columns)}")

            df_json['createdAt'] = pd.to_datetime(df_json['createdAt'])
            return df_json[required_columns].sort_values(by="createdAt")
        except KeyError as e:
            raise ValueError(f"Error processing JSON to DataFrame: {e}")
        except Exception as e:
            raise RuntimeError(f"Unexpected error in json_to_df: {e}")

class ActionsArtifacts:
    """
    A class to handle downloading, retrieving, and deleting GitHub Actions artifacts.
    """

    def __init__(self, jobIds: list, repository: str):
        """
        Initializes the ActionsArtifacts object.

        :param repository: The GitHub repository in the format "owner/repo".
        """
        self.repository = repository
        self.folder = 'artifacts/'  # Default storage dir
        self.paths = self.retrieve_downloaded_artifacts() 
        self.jobIds: set = set(jobIds)
        self.download_artifact()

    def download_artifact(self: str):
        """
        Downloads an artifact from GitHub Actions using the GitHub CLI.

        :param database_id: The database ID of the artifact to download.
        """
        try:
            # Ensure the folder exists before downloading
            os.makedirs(self.folder, exist_ok=True)
            # Finding the artifacts that have yet to be downloaded
            downloaded_paths = set(int(p.split('/')[1]) for p in self.paths)
            to_download = self.jobIds.difference(downloaded_paths)

            for database_id in to_download:
            # Construct the command to download the artifact
                command=f'gh run --repo {self.repository} download {database_id} --dir {os.path.join(self.folder, str(database_id))}'
                subprocess.run(command, shell=True, text=True, check=False, capture_output=True)
        except Exception as e:
            print(f"Unexpected error: {e}")

    def retrieve_downloaded_artifacts(self) -> list[str]:
        """
        Retrieves all downloaded artifacts file paths.

        :return: returns Paths of the downloaded artifacts
        """
        paths = []

        # Walk through the artifacts folder and collect all file paths
        for path, _, files in os.walk(self.folder):
            for file in files:
                paths.append(os.path.join(path, file))

        return paths

    def delete_downloaded_artifacts(self):
        """
        Deletes all downloaded artifacts recursively
        """
        try:
            shutil.rmtree(self.folder)
            if os.path.exists(self.folder):
                print("Error: Failed to delete artifacts directory.")
            else:
                print("Artifacts directory deleted successfully.")
        except FileNotFoundError:
            print("Artifacts directory not found, nothing to delete.")
        except Exception as e:
            print(f"Error while deleting artifacts: {e}")

class ActionsWorkflow:
    """
    A class to extract GitHub Actions workflows using the GitHub CLI, generating a dataframe with returned data
    """

    def __init__(self, repository, query_size):
        """
        Initializes the ActionsWorkflow class.

        :param repository: GitHub repository in the format "owner/repo".
        :param query_size: Number of workflows to retrieve.
        """
        self.repository = repository
        self.json_attributes = '--json name,status,conclusion,createdAt,databaseId,workflowDatabaseId'
        self.query_size = query_size
        self.df = self.__gh_list_query__()

    def __gh_list_query__(self):
        """
        Calls the GitHub API via the GitHub CLI (`gh run list`) and retrieves
        a specified number of workflows.

        :return: A DataFrame containing the parsed workflow data.
        """
        try:

            list_command = f'gh run --repo {self.repository} list {self.json_attributes} -L {self.query_size}'
            
            output_json = subprocess.run(
                list_command, shell=True, text=True, check=True, capture_output=True
            ).stdout

            parsed_json = ArqManipulation.parse_stdout_json(output_json)
            df = ArqManipulation.json_to_df(parsed_json)

            saved_parquet_df = ArqManipulation.read_parquet_file(paths.get('workflow'))
            df_cleared = pd.concat([saved_parquet_df, df], axis=0, ignore_index=True).drop_duplicates()
        
            ArqManipulation.save_df_to_parquet(df = df_cleared, parquet_file_name=paths.get('workflow'))

            return df.set_index('name')

        except subprocess.CalledProcessError as e:
            print(f"Error executing GitHub CLI command: {e}")
            return pd.DataFrame()  # Return an empty DataFrame on error

class ActionsJobs:
    """
    A class to interact with GitHub Actions jobs using the GitHub CLI.
    """

    def __init__(self, repository):
        """
        Initializes the ActionsJobs class.

        :param repository: GitHub repository in the format "owner/repo".
        :param workflow: Workflow associated with the jobs.
        """
        self.repository = repository

    def __retrieve_jobs__(self, database_id: int):
        command = f'gh run --repo {self.repository} view {database_id}'
        jobs_data = subprocess.run(command, shell=True, text=True, check=True, capture_output=True).stdout

        return jobs_data

    def get_jobs(self, database_id: int) -> pd.DataFrame:
            """
            Retrieves job data from the GitHub CLI and processes it.

            :param database_id: The ID of the workflow run.
            :return: A Pandas DataFrame containing job details.
            """
            try:
                saved_parquet_df = ArqManipulation.read_parquet_file(parquet_file_name=paths.get('jobs'))
                jobs_df = pd.DataFrame()

                if saved_parquet_df.empty:
                    data = self.__retrieve_jobs__(database_id=database_id)
                    jobs_df = self.__clean_job_text__(data)

                    jobs_df["databaseId"] = int(database_id)

                    ArqManipulation.save_df_to_parquet(jobs_df, parquet_file_name=paths.get('jobs'))

                elif database_id not in saved_parquet_df['databaseId'].values:
                    data = self.__retrieve_jobs__(database_id=database_id)
                    data_df = self.__clean_job_text__(data)
                    data_df["databaseId"] = int(database_id)

                    jobs_df = pd.concat([saved_parquet_df, data_df], axis=0, ignore_index=True).drop_duplicates()
                    ArqManipulation.save_df_to_parquet(jobs_df, parquet_file_name=paths.get('jobs'))

                return pd.concat([saved_parquet_df, jobs_df])

            except subprocess.CalledProcessError as e:
                print(f"Error executing GitHub CLI command: {e}")
                return pd.DataFrame()

            except Exception as e:
                print(f"Unexpected error: {e}")
                return pd.DataFrame()
        
    def __split_string__(self, job_list):
        """
        Splits a job string into structured components.

        :param job: The job string to split.
        :return: A list of cleaned job attributes.
        """
        jobs = []

        for job in job_list:
            delimiters = r" \| | / build in | \(ID |\| in| / cleanup in | /| in " 
            splitted_job = re.split(delimiters, job)
            splitted_job = [s.strip() for s in splitted_job if s.strip()]
            jobs.append(splitted_job)
        
        jobs.pop(0)

        return jobs

    def __build_cleaned_df__(self, data):
        # Define columns
        columns = ["conclusion", "test", "buildTime (sec)", "jobId"]
        jobs_df = pd.DataFrame(columns=columns)
        jobs_df["failedAt"] = None

        for job in data:
            if any("ID" in item and ("PASSED" in item or "FAILED" in item) for item in job):
                temp_df = pd.DataFrame(self.__split_string__(job), columns=columns)

                temp_df['buildTime (sec)'] = temp_df['buildTime (sec)'].apply(str_time_to_int)
                jobs_df = pd.concat([jobs_df, temp_df], ignore_index=True)
            
            elif any("FAILED" in item for item in job):
                failed = next(item for item in job if "FAILED" in item).split("FAILED | ")
                if not jobs_df.empty:
                    jobs_df.at[jobs_df.index[-1], "failedAt"] = failed[1]  

        jobs_df["jobId"] = jobs_df["jobId"].str.rstrip(")").astype('int')
        return jobs_df

    def __find_jobs__(self, base_str: str) -> list[str]:
        lines = base_str.splitlines()
        arr = []  # Stores grouped sections
        current_group = []  # Temporary storage for the current section

        for line in lines:
            if line.isupper() or not line.strip():  # New section (uppercase or empty line)
                if current_group:  # Avoid adding empty groups
                    arr.append(current_group)
                current_group = [line]  # Start a new group
            else:
                current_group.append(line)

        if current_group:  # Append the last group
            arr.append(current_group)

        # Filter out groups that do not start with an uppercase title
        filtered_arr = [group for group in arr if group and group[0].isupper()]
        return filtered_arr

    def __clean_job_text__(self, base_str: str) -> pd.DataFrame:
        """
        Cleans and structures GitHub job data from CLI output.

        :param base_str: Raw job text output from the GitHub CLI.
        :return: A Pandas DataFrame with structured job data.
        """
        try:
            # Remove ANSI escape sequences and unwanted characters
            ansi_cleaned = ArqManipulation.clean_ansi_escape(base_str)
            cleaned = ansi_cleaned.replace("✓", "PASSED |").replace("X", "FAILED |")

            stripped_list = self.__find_jobs__(cleaned)

            if not (x.find('JOBS') or x.find("ANNOTATIONS") for x in stripped_list):
                return pd.DataFrame()

            jobs_df = self.__build_cleaned_df__(stripped_list)

            return jobs_df

        except Exception as e:
            print(f"Error processing job text: {e}")
            return pd.DataFrame()

def str_time_to_int(time_str: str) -> int:
    """
    Converts a time string to seconds.
    returns: int
    """
    names = ['d', 'h', 'm', 's']
    seconds = [86400, 3600, 60, 1]

    total_time = 0

    for m, t in zip(names,seconds):
        if m in time_str:
            time_list = time_str.split(m)
            total_time +=  int(time_list[0]) * t
            time_str = time_list[1]

    return total_time

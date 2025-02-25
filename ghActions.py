import pandas as pd
import json
import subprocess
import re
import os


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
                print(f"File '{parquet_file_name}' does not exist.")
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
            print(f"DataFrame successfully saved to {parquet_file_name}")
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

            ArqManipulation.save_df_to_parquet(df = df, parquet_file_name="./bin/actionsWorflow.parquet")

            return df.set_index('name')

        except subprocess.CalledProcessError as e:
            print(f"Error executing GitHub CLI command: {e}")
            return pd.DataFrame()  # Return an empty DataFrame on error


class ActionsJobs:
    """
    A class to interact with GitHub Actions jobs using the GitHub CLI.
    """

    def __init__(self, repository, workflow):
        """
        Initializes the ActionsJobs class.

        :param repository: GitHub repository in the format "owner/repo".
        :param workflow: Workflow associated with the jobs.
        """
        self.repository = repository
        self.workflow = workflow  

    def __split_string__(self, job):
        """
        Splits a job string into structured components.

        :param job: The job string to split.
        :return: A list of cleaned job attributes.
        """
        delimiters = r" \| | / build in | \(ID |\| in| / cleanup in | /" 
        splitted_job = re.split(delimiters, job)
        splitted_job = [s.strip() for s in splitted_job if s.strip()]

        return splitted_job


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
            
            # Extract job details section
            start_index = cleaned.find("JOBS")
            end_index = cleaned.find("ANNOTATIONS")
            if start_index == -1 or end_index == -1:
                print("Warning: JOBS or ANNOTATIONS section not found in output.")
                return pd.DataFrame()

            cleaned_list = cleaned[start_index:end_index].splitlines()

            # Define columns
            columns = ["Conclusion", "Test", "Build_Time", "Job_Id"]
            jobs_df = pd.DataFrame(columns=columns)
            jobs_df["Failed_At"] = None

            for job in cleaned_list:
                if "ID" in job and ("PASSED" in job or "FAILED" in job):
                    temp_df = pd.DataFrame([self.__split_string__(job)], columns=columns)
                    temp_df['Build_Time'] = str_time_to_int(temp_df['Build_Time'].get(0))
                    jobs_df = pd.concat([jobs_df, temp_df], ignore_index=True)
                
                elif "FAILED" in job:
                    failed = job.split("FAILED | ")
                    if not jobs_df.empty:
                        jobs_df.at[jobs_df.index[-1], "Failed_At"] = failed[1]  

            jobs_df["Job_Id"] = jobs_df["Job_Id"].str.replace(")", "", regex=False).astype('int')

            return jobs_df

        except Exception as e:
            print(f"Error processing job text: {e}")
            return pd.DataFrame()

    def get_jobs(self, database_id):
        """
        Retrieves job data from the GitHub CLI and processes it.

        :param database_id: The ID of the workflow run.
        :return: A Pandas DataFrame containing job details.
        """
        try:
            jobs_df = ArqManipulation.read_parquet_file(parquet_file_name="./bin/actionsJobs.parquet")
            if jobs_df.empty and database_id in jobs_df['Database_Id'].values:
                command = f'gh run --repo {self.repository} view {database_id}'
                jobs_data = subprocess.run(command, shell=True, text=True, check=True, capture_output=True).stdout

                jobs_df = pd.concat([jobs_df, self.__clean_job_text__(jobs_data)], ignore_index=True)

                if not jobs_df.empty:
                    jobs_df["Database_Id"] = int(database_id)
                ArqManipulation.save_df_to_parquet(jobs_df, parquet_file_name="./bin/actionsJobs.parquet")

            return jobs_df

        except subprocess.CalledProcessError as e:
            print(f"Error executing GitHub CLI command: {e}")
            return pd.DataFrame()

        except Exception as e:
            print(f"Unexpected error: {e}")
            return pd.DataFrame()

def str_time_to_int(time_str):
    names = ['d', 'h', 'm', 's']
    seconds = [86400, 3600, 60, 1]

    total_time = 0

    for m, t in zip(names,seconds):
        if m in time_str:
            time_list = time_str.split(m)
            total_time +=  int(time_list[0]) * t
            time_str = time_list[1]

    return total_time


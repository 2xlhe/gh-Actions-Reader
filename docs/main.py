import LogExtractor as extractor
import pandas as pd
import argparse
from docs.createPdf import PdfMaker
from actions import ActionsWorkflow, ActionsJobs, ActionsArtifacts
import re


def get_ids_in_date_range(df, initial_date, final_date):
    # Convert the date strings to datetime objects with UTC timezone
    initial_date = pd.to_datetime(initial_date, format="%d-%m-%Y").tz_localize('UTC')
    final_date = pd.to_datetime(final_date, format="%d-%m-%Y").tz_localize('UTC')
    
    filtered_df = df[(df['createdAt'] >= initial_date) & (df['createdAt'] <= final_date)]

    return filtered_df['databaseId'].tolist()


def regex_type(pattern: str | re.Pattern):
    """Argument type for matching a regex pattern."""

    def closure_check_regex(arg_value):  
        if not re.match( pattern, arg_value):
            raise argparse.ArgumentTypeError("invalid value")
        return arg_value

    return closure_check_regex


def pdf_params():

    parser = argparse.ArgumentParser()
    parser.add_argument('--repo_path', 
                        required=True, 
                        type=regex_type(r"[A-Z0-9a-z-]+\/[A-Z0-9a-z-]+\/*"))
    parser.add_argument('--query_size', 
                        required=False,
                        type=int,
                        default=20,
                        help='Default query size 20')
    parser.add_argument('--initial_date', 
                        required=True,
                        type=regex_type(r"[0-9]{2}-[0-9]{2}-[0-9]{4}"), 
                        help='Date of the first query')
    parser.add_argument('--final_date',
                        required=True, 
                        type=regex_type(r"[0-9]{2}-[0-9]{2}-[0-9]{4}"), 
                        help='Date of the last query')

    return parser.parse_args()


    

if __name__ == '__main__':
    args = pdf_params()

    print('Querying Workflows...')
    workflow = ActionsWorkflow(repository=args.repo_path, query_size=args.query_size)
    workflowIds = get_ids_in_date_range(workflow.df, args.initial_date, args.final_date)

    print("Retrieving workflow Jobs...")
    jobs = ActionsJobs(args.repo_path)

    all_workflows_jobs = pd.DataFrame()

    for id in set(workflowIds):
        all_workflows_jobs = pd.concat([all_workflows_jobs, jobs.get_jobs(id)])

    print("Getting available artifacts...")
    artifacts = ActionsArtifacts(workflowIds, repository=args.repo_path)
    all_tests_df = pd.DataFrame()
    all_times_df = pd.DataFrame()
    all_failures_df = pd.DataFrame()

    for path in artifacts.paths:
        artifact = extractor.PytestArtifactLogExtractor(path)
        pytest_tests_status	, pytest_run_times, pytest_failures_errors = artifact.log_to_df()
        all_tests_df = pd.concat([all_tests_df, pytest_tests_status]).drop_duplicates()
        all_times_df = pd.concat([all_times_df, pytest_run_times]).drop_duplicates()
        all_failures_df = pd.concat([all_failures_df, pytest_failures_errors]).drop_duplicates()

    print("Generating Pdf...")
    p = PdfMaker(all_tests_df, all_times_df, all_failures_df)
    p.create_pdf()
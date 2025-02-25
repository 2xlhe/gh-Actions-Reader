from actions import ActionsWorkflow, ActionsJobs, ActionsArtifacts
import LogExtractor as extractor
import pandas as pd
from CreatePdf import PdfMaker

def get_ids_in_date_range(df, initial_date, final_date):
    # Convert the date strings to datetime objects with UTC timezone
    initial_date = pd.to_datetime(initial_date, format="%d-%m-%Y").tz_localize('UTC')
    final_date = pd.to_datetime(final_date, format="%d-%m-%Y").tz_localize('UTC')
    
    filtered_df = df[(df['createdAt'] >= initial_date) & (df['createdAt'] <= final_date)]

    return filtered_df['databaseId'].tolist()

if __name__ == '__main__':
    repo_path = 'MagaluCloud/s3-specs'
    query_size = 4

    print('Querying Workflows...')
    workflow = ActionsWorkflow(repository=repo_path, query_size=query_size)

    initial_date = "16-01-2025"
    final_date = "21-03-2025"
    workflowIds = get_ids_in_date_range(workflow.df, initial_date, final_date)

    print("Retrieving workflow Jobs...")
    jobs = ActionsJobs(repo_path)

    all_workflows_jobs = pd.DataFrame()

    for id in set(workflowIds):
        all_workflows_jobs = pd.concat([all_workflows_jobs, jobs.get_jobs(id)])

    print("Getting available artifacts...")
    artifacts = ActionsArtifacts(workflowIds, repository=repo_path)
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
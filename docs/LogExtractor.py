from actions import ArqManipulation
import pandas as pd
import re
from numpy.lib.stride_tricks import sliding_window_view as swv


paths = {
    'status':'./bin/pytest.status.log.parquet',
    'categories':'./bin/pytest.categories.log.parquet',
    'failures':'./bin/pytest.failures.log.parquet',
    }

class PytestArtifactLogExtractor:
    """f
    A class to extract and process test status and timing information from a pytest artifact log.
    """
    def __init__(self, path: str):
        """
        Initializes the PytestArtifactLogExtractor object.

        :param path: Path to the pytest artifact log file.
        """
        self.path = path
        self.data = self.__read_file__()

    def __read_file__(self):
        """
        Reads the contents of the log file and returns it as a string.

        :return: String containing the file content.
        """
        with open(self.path, "r") as file: 
            data = file.read()

        return ArqManipulation.clean_ansi_escape(data)

    def log_to_df(self):
        """
        Parses the log file to extract test results and performance metrics.

        :return: A DataFrame combining test statuses with time metrics.
        """

        # Retrieving databaseID out of path
        databaseId = self.__extract_self_path_info__().get('databaseId').get(0)
        databaseId = int(databaseId) if databaseId else 000000
    
        # Checking if artifacts is not already stored
        df_status_parquet = ArqManipulation.read_parquet_file(parquet_file_name=paths.get('status'))   
        df_categories_parquet = ArqManipulation.read_parquet_file(parquet_file_name=paths.get('categories'))   
        df_failures_parquet = ArqManipulation.read_parquet_file(parquet_file_name=paths.get('failures'))   

        # Creating dataframes test status and categories
        tests, categories, failures = self.__extract_all_categories__()
        status_df = self.__create_status_df__(tests)
        categories_df = self.__create_time_df__(categories)
        failures_df = self.__create_failure_df__(failures)

        # Labeling the dfs
        status_df.index.name = 'pytest_tests_status'
        categories_df.index.name = 'pytest_run_times'
        failures_df.index.name = 'pytest_failures_errors'

        # Applying individual id for each table
        status_df['databaseId'] = databaseId
        categories_df['databaseId'] = databaseId
        failures_df['databaseId'] = databaseId
 

        # Since there is data on the parquets, concatenating both
        concated_dfs = (pd.concat([df_status_parquet, status_df], axis=0).drop_duplicates(),
                        pd.concat([df_categories_parquet, categories_df], axis=0).drop_duplicates(), 
                        pd.concat([df_failures_parquet, failures_df], axis=0).drop_duplicates()
                        )   
         

        # Save the concatenated DataFrames back to Parquet files
        ArqManipulation.save_df_to_parquet(df=concated_dfs[0], parquet_file_name=paths.get('status'))
        ArqManipulation.save_df_to_parquet(df=concated_dfs[1], parquet_file_name=paths.get('categories'))
        ArqManipulation.save_df_to_parquet(df=concated_dfs[2], parquet_file_name=paths.get('failures'))

        return concated_dfs

    def __get_list_by_name__(self, data: list, name: str):
        """
        Find the sublist containing the specified name in the first element.

        :param data: A list of sublists to search through.
        :type data: list[list]
        :param name: The name to search for in the first element of each sublist.
        :type name: str
        :return: A list of sublists where the first element matches the name.
        :rtype: list[list]
        """
        matching_sublists = []
        
        for sublist in data:
            if re.search(name, sublist[0]):  # Converte os itens para string
                matching_sublists.append(sublist)
        
        return matching_sublists

    def __extract_all_categories__(self):
        """
        Converts extracted timing data into DataFrames.

        :param values: A list of lists with extracted time metrics.
        :type values: list[list]
        :return: A list of DataFrames with execution time statistics.
        :rtype: list[pandas.DataFrame]
        """
        header = []
        # Filtering out irrelevant categories
        keywords = ('deselected', 'passed in', 'grand total', 'live log')

        # Breaking each file into an list that contains the category as the pos 0
        values = self.data.splitlines()
        for value in values:
            if any(k in value for k in keywords):
                continue   
            elif re.match(r'=+|-+', value): # Divide by headers demarked by '=' or '-' (logging)
                value = value.replace("=", "")  
                value = value.replace("-", "")  
                header.append([value]) 
            else:
                # Populate each category and break in the case of the pytest-durations tables while ignoring empty values
                header[-1].append(value)

        headers = [['live_log','live_log','live_log']]
        # Ignore cases of logging mode is active
        if not 'live log' in self.data:
            headers = self.__extract_test_status_names__(self.__get_list_by_name__(header, 'test session')[0])    
        categories = self.__extract_time_categories__(self.__get_list_by_name__(header, 'duration top'))
        failures = self.__extract_failures_errors__(self.__get_list_by_name__(header, 'summary'))

        return headers, categories, failures

    def __extract_test_status_names__(self, data):
        """
        Extracts the status and the tests names out of the pytest log, breaking them down to a list of lists.

        :param data: A list of lines containing test results.
        :type data: list[str]
        :return: list[list[str]]: A list of lists with test names, statuses (PASSED, FAILED, ERROR), and additional details.
        """

        tests = []
        keywords = ('PASSED', 'FAILED', 'ERROR', 'SKIPPED')

        for line in data:
            if any(k in line for k in keywords):
                match = re.search(r'(PASSED|FAILED|ERROR).*', line).group()
                # Splitting the Keyword NameTest from category and argument
                match = re.split(r'::', match, 1)
                tmp = re.split('\s', match[0], maxsplit=1)
                # Splitting the category from arguments
                tmp += re.split(r'\[', match[1], maxsplit=1)
                # Allow degenerated data to fit in the dataframe
                while(len(tmp) < 4):
                    tmp.append(None)

                tests.append(tmp)

        return tests
    
    def __extract_time_categories__(self, data):
        categories = []
        for d in data:
            categories.append([])
            for s in d: 
                formatted_s = list(filter(None,s.split(" ")))
                if 'duration' in formatted_s: #converting the header name back into string
                    formatted_s = ' '.join(formatted_s)
                categories[-1].append(formatted_s)

        return categories

    def __extract_failures_errors__(self, data):

        """
        Extracts from the pytest log the details of tests with failures or errors cleaning the data to make it ready to a dataframe.

        :param data: A list of strings containing test results.
        :type data: list[str]
        :return: list[list]: A list of lists containing details of tests with failures and/or errors.
        """
        # Some test wont have errors, but there still need a dataframe
        if not data:
            return [[None]*5]


        keywords = ['PASSED','FAILED','ERROR']
        failures = []
        
        for line in data[0]:
            if any(k in line for k in keywords):
                match = re.search(r'(PASSED|FAILED|ERROR).*', line).group()
                # Splitting the Keyword NameTest from category and argument
                match = re.split(r'::', match, 1)
                tmp = re.split('\s', match[0], maxsplit=1)
                # Splitting the category from arguments
                tmp1 = re.split(r'\[', match[1], maxsplit=1)
                tmp2 = re.split(r'\] - ', tmp1[1], maxsplit=1)
                
                # Splitting error name from its description
                tmp.append(tmp1[0])
                tmp += re.split(r':| ', tmp2[1], maxsplit=1)

                # Allow degenerated data to fit in the dataframe
                while(len(tmp) < 5):
                    tmp.append(None)

                failures.append(tmp)

        return failures

    def __create_status_df__(self, data):
        formatted_data = []

        try:
            for d in data:
                if 'live_log' not in d:
                    formatted_data.append(d)

            df = pd.DataFrame(formatted_data, columns=["status", "category", "name", "arguments"])
            df['name'] = df['name'].astype(str).str.replace(" ", "", regex=True)
            df = df.set_index('name')
        except:
            print('None Type')
            return pd.DataFrame()
        return df

    def __create_time_df__(self, data):
        """
        Converts extracted timing information into DataFrames.

        :param values: A list of lists containing extracted time metrics.
        :return: A list of DataFrames with execution time statistics.
        """
        dfs = pd.DataFrame()
        
        for h in data:
            time_df = pd.DataFrame(h[2:], columns=h[1])

            # Converting time-related columns to datetime.time format
            time_columns = ['avg', 'min', 'total']
            for col in time_columns:
                if col in time_df.columns:
                    time_df[col] = pd.to_timedelta(time_df[col], errors='coerce').dt.total_seconds().round(3)
                    
            # Assigning a 'durationType' column for metric categorization
            time_df['durationType'] = h[0].replace('top', '').replace('test', '')

            dfs = pd.concat([time_df, dfs], ignore_index=True)

        if 'name' in dfs.columns:
            dfs = dfs.set_index('name')

        return dfs

    def __create_failure_df__(self, data):
        return pd.DataFrame(data, columns=['status', 'category', 'name', 'error', 'error_details']).set_index('name').dropna()

    def __extract_self_path_info__(self):
        """
        Extracts test and database ID information from the log file path.

        :return: A DataFrame containing 'test' and 'databaseId' information.
        """
        # Extract filename without extension
        stripped = self.path.split('/')[-1].split('.')
        stripped.pop()  # Remove the file extension

        # Ensure there are exactly three elements (fill missing ones with None)
        while len(stripped) < 3:
            stripped.append(None)  # Fill missing values with NaN

        # Create DataFrame
        df = pd.DataFrame([stripped], columns=['test', 'region', 'databaseId'])

        return df

    def __merge_artifact_dfs__(self, times_df, status_df):
        """
        Merges test execution time data with test status information.

        :param times_df: A list of DataFrames containing time-related data.
        :param status_df: A DataFrame containing test statuses.
        :return: A combined DataFrame containing execution metrics and test results.
        """
        databaseId_df = self.__extract_self_path_info__()  
        order = ['category', 'durationType', 'databaseId', 'status', 'num', 'avg', 'min', 'total']
        dfs = []

        for h in times_df:
            joined_df = h.join(status_df)  # Merging time metrics with test statuses

            # Adding database ID to each row
            for col in databaseId_df.columns.values:
                joined_df[col] = databaseId_df[col].values[0]  

            # Reordering columns
            joined_df = joined_df[order]  
            dfs.append(joined_df)

        return pd.concat(dfs)  
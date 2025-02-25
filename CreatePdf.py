
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, ListFlowable, ListItem, Spacer, Image
from datetime import datetime

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import tempfile

class PdfDataPlotter:
    def __init__(self, status_df, categories_df, failures_df):
        self.status_df = status_df
        self.categories_df = categories_df
        self.failures_df = failures_df

        self.category_status_df = self.status_df[['category', 'status']]

    def error_distribution_pie_chart(self):
        error_distribution_df = self.status_df

        # Filter for FAILED status
        failed_df = error_distribution_df[error_distribution_df['status'] == 'FAILED']

        # Group by category and count the number of FAILED statuses
        failed_counts = failed_df.groupby('category').size().reset_index(name='count')

        # Create the pie chart
        fig = px.pie(
            failed_counts, 
            names="category",  # Use 'category' for pie slice labels
            values="count",    # Use 'count' for pie slice sizes
            title="Distribuição de falhas por categoria",
            color_discrete_sequence=px.colors.sequential.RdBu,
        )

        fig.update_layout(
        #   width=400,  # Set the width of the plot (in pixels)
        #  height=400,  # Set the height of the plot (in pixels)
            margin=dict(l=20, r=20, t=40, b=20)  # Adjust margins if needed
        )

        # Make the pie chart circle bigger by adjusting the marker size
        fig.update_traces(
            marker=dict(line=dict(color='white', width=2)),  # Optional: Add a white border
            textposition='inside',  # Display text inside the slices
            textinfo='percent+label'  # Show percentage and label
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            fig.write_image(tmpfile.name, format="png", width=800, height=400)
            return tmpfile.name
    
    def plot_category_errors_bar(self):
        # Calculate the frequency of errors per category
        error_freq_df = self.failures_df.groupby(['category', 'error']).size().reset_index(name='frequency')

        # Create the bar plot
        fig = px.bar(
            error_freq_df, 
            x="category", 
            y="frequency", 
            color="error",  # Use a discrete color sequence
            color_discrete_sequence=px.colors.sequential.RdBu,
            title="Frequência de tipos de erros por categoria",
            labels={'frequency': 'Frequency of Errors', 'category': 'Category'},
        )

        # Adjust layout to control bar width
        fig.update_layout(
            xaxis_title="Category",
            yaxis_title="Frequency of Errors",
            barmode='stack',  
            bargroupgap=0.1,  
            width=600,
            margin=dict(l=20, r=20, t=40, b=20)  
        )

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            fig.write_image(tmpfile.name, format="png", width=800, height=400)
            return tmpfile.name

    def categories_failures_passed_rate(self):
        # Group by status and category, then calculate value counts
        total_category = self.category_status_df.groupby(['status', 'category']).value_counts()

        # Create a DataFrame for FAILED and PASSED counts, filling missing values with 0
        status_freq_df = pd.DataFrame([total_category.FAILED, total_category.PASSED]).fillna(0).astype(int).T
        status_freq_df.columns = ['FAILED', 'PASSED']
        status_freq_df = status_freq_df.reset_index()

        # Calculate total, passed percentage, and failed percentage
        status_freq_df['TOTAL'] = status_freq_df['PASSED'] + status_freq_df['FAILED']
        status_freq_df['PASSED_PCT'] = (status_freq_df['PASSED'] / status_freq_df['TOTAL']) * 100
        status_freq_df['FAILED_PCT'] = (status_freq_df['FAILED'] / status_freq_df['TOTAL']) * 100

        # Transform the DataFrame from wide to long format for plotting
        status_freq_long = status_freq_df.melt(
            id_vars=['category'], 
            value_vars=['PASSED_PCT', 'FAILED_PCT'], 
            var_name='Status', 
            value_name='Percentage'
        )

        # Add real values for display in the plot
        status_freq_long['Real Value'] = status_freq_long.apply(
            lambda row: status_freq_df.loc[status_freq_df['category'] == row['category'], row['Status'].replace('_PCT', '')].values[0], 
            axis=1
        )

        # Create a stacked bar plot
        fig = px.bar(
            status_freq_long.round(2), 
            x="category", 
            y="Percentage", 
            color="Status", 
            barmode='stack', 
            title="Proporção de testes Aprovados/Falho",
            labels={'Percentage': 'Percentage'},
            text=status_freq_long["Real Value"]  # Display real values on bars
        )

        # Adjust layout to display values inside bars
        fig.update_traces(texttemplate='%{text}', textposition='inside')
        fig.update_yaxes(title='Porcentagem')
        fig.update_xaxes(title='Categoria')

        # Save the plot to a temporary file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmpfile:
            fig.write_image(tmpfile.name, format="png", width=800, height=400)
            return tmpfile.name

class PdfMaker:
    def __init__(self, status_df, categories_df, failures_df):
        self.status_df = status_df
        self.categories_df = categories_df
        self.failures_df = failures_df
        self.metrics_df = self.__create_df__()
        self.plotter = PdfDataPlotter(status_df=status_df, categories_df=categories_df, failures_df=failures_df)
        
        styles = getSampleStyleSheet()
        self.styles = {
            'heading1': styles['Heading1'],
            'normal': styles['Normal'],
            'bold': ParagraphStyle(
                name="Bold",
                parent=styles['Normal'],
                fontName="Helvetica-Bold",
                fontSize=12
            )
        }

        # Define dimensions
        self.dim = {
            'width': A4[0],
            'height': A4[1],
            'margin': 0.1 * A4[0],  # Use A4[0] directly to avoid circular dependency
        }

    def get_time(self, metric):
        return pd.Series(dict(map(lambda t, x: (x, self.categories_df.loc[self.categories_df.index == t, metric].sum()), self.status_df.index.unique(), self.status_df.category.unique())))

    def __create_df__(self):
        # Setup
        error_passed_info = self.status_df.groupby(['status','category'])
        status_freq_df = pd.DataFrame([error_passed_info.value_counts().FAILED, error_passed_info.value_counts().PASSED]).fillna(0).astype(int).reset_index().T
        status_freq_df.columns = ['FAILED','PASSED']

        # Count the total duration of each category
        count_df = error_passed_info.size().unstack('status').fillna(0).astype(int)
        count_df['total'] = count_df.sum(axis=1)

        total_times = self.get_time('total')
        avg_time_test = self.get_time('avg')
        min_test_time  = self.get_time('min')

        time_count_df = pd.concat([count_df['PASSED'], 
                                   count_df['FAILED'], 
                                   count_df['total'], 
                                   min_test_time, 
                                   avg_time_test, 
                                   total_times], axis=1)
        
        time_count_df.columns = ['num_passed', 'num_failed', 'total_runs', 'min_test_time', 'avg_test_time', 'total_duration']
        time_count_df['avg_test_time'] = (time_count_df['avg_test_time'] / time_count_df['total_runs']).round(2) 

        report_df = pd.DataFrame({'name': self.status_df['category'].unique()}).set_index('name')
        return  pd.concat([report_df, time_count_df], axis=1).reset_index().drop_duplicates().round(2)
    
    def create_pdf(self):

        # Create PDF with margins
        doc = SimpleDocTemplate("report_v0.pdf", pagesize=A4,
                                leftMargin=self.dim['margin'], rightMargin=self.dim['margin'], topMargin=0.1*self.dim['height'], bottomMargin=0.1*self.dim['height'])

        # Create the story (content) for the PDF
        story = []

        # Add title with fields
        story.extend(self.create_title())

        # Add each section to the story
        story.extend(self.create_execution_summary())
        story.extend(self.create_detailed_results())
        story.extend(self.create_errors_summary())
        story.extend(self.create_graphs())

        # Build PDF
        doc.build(story)

    def create_title(self):
        # Initialize the story list
        story = []

        # Get current date and time
        agora = datetime.now()
        horario_dia = agora.strftime("%d/%m/%Y %H:%M:%S")

        # Create the title
        title_text = "Sumário de Resultados dos Testes"
        title_paragraph = Paragraph(f"<b>{title_text}</b>", self.styles['heading1'])


        # Add title and date to the story as separate elements
        story.append(title_paragraph)

        # Create the formatted text for the execution date, system version, and environment
        execution_paragraph = Paragraph(f"Data da Execução: {horario_dia}", self.styles['normal'])
        version_paragraph = Paragraph("Versão do Sistema: ", self.styles['normal'])
        environment_paragraph = Paragraph("Ambiente: ", self.styles['normal'])

        # Add other paragraphs to the story
        story.append(execution_paragraph)
        story.append(Spacer(1, 6))  # Spacer between execution and version
        story.append(version_paragraph)
        story.append(Spacer(1, 6))  # Spacer between version and environment
        story.append(environment_paragraph)

        story.append(Spacer(1, 18))  # Add space at the end

        # Return the complete story
        return story

    def create_execution_summary(self):
        story = []
        story.append(Paragraph("Resumo Geral", self.styles['bold']))
        story.append(Spacer(1, 6))

        fail_success_rate = (self.metrics_df['num_failed'].sum() / self.metrics_df['num_passed'].sum() * 100).round(2)

        # Criando a lista de resumo corretamente
        summary_data = {
            'Total de Testes:': self.metrics_df['total_runs'].sum(),
            'Testes Bem-Sucedidos:': self.metrics_df['num_passed'].sum(),
            'Testes com Falha:': self.metrics_df['num_failed'].sum(),
            'Taxa de Sucessos/Falha:': f"{fail_success_rate}%",  # Round to 2 decimal places
            'Tempo Mínimo de Execução:': f"{self.metrics_df['min_test_time'].min():.2f} s",
            'Tempo Médio de Execução:': f"{self.metrics_df['avg_test_time'].mean():.2f} s",
            'Duração Total dos Testes:': f"{self.metrics_df['total_duration'].sum():.2f} s"
        }

        # Criando a lista com bullet points
        bullet_points = [
            ListItem(Paragraph(f"<b>{key}</b> {value}", self.styles['normal']), leftIndent=20, spaceAfter=6)
            for key, value in summary_data.items()
        ]

        # Criando o ListFlowable
        list_flowable = ListFlowable(bullet_points, bulletType='bullet', leftIndent=20)

        # Adicionando ao relatório
        story.append(list_flowable)
        story.append(Spacer(1, 24))

        return story

    def create_detailed_results(self):
        story = []
        story.append(Paragraph("Detalhamento dos Testes", self.styles['bold']))
        story.append(Spacer(1, 12))
        df_renamed = self.metrics_df.copy() 
        df_renamed.columns = [
            'Categoria de Teste', 
            'Testes Bem-Sucedidos', 
            'Falhas', 
            'Execuções', 
            'Tempo Mínimo de Execução', 
            'Tempo Médio', 
            'Duração Total'
        ]


        df_renamed = df_renamed.drop(columns=['Tempo Mínimo de Execução'])

        df_renamed['Tempo Médio'] = df_renamed['Tempo Médio'].astype(str) + ' sec'
        df_renamed['Duração Total'] = df_renamed['Duração Total'].astype(str) + ' sec'

        # Prepare the detailed data for the table
        detailed_tests_data = [[Paragraph(str(value), self.styles['normal']) for value in df_renamed.columns.tolist()]]  # Add header
        detailed_tests_data.extend(
            [[Paragraph(str(value), self.styles['normal']) for value in row] for row in df_renamed.values.tolist()]
        )

        # Calculate available width after applying margins
        available_width = self.dim['width'] - 2 * self.dim['margin']  

        # Define column proportions
        proportions = [0.3, 0.15, 0.15, 0.15, 0.2, 0.15] 

        total_proportion = sum(proportions)
        if total_proportion > 1:
            proportions = [p / total_proportion for p in proportions]  

        # Calculate column widths based on width
        col_widths = [available_width * p for p in proportions]

        # Create the table
        detailed_table = Table(detailed_tests_data, colWidths=col_widths)
        detailed_table.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                            ('GRID', (0, 0), (-1, -1), 0.5, colors.black)]))
        story.append(detailed_table)
        story.append(Spacer(1, 24))

        return story

    def create_errors_summary(self):
        """
        Creates a summary of errors in a PDF document.

        :param df: DataFrame containing error data.
        :param normal_style: Style for normal text.
        :param bold_style: Style for bold text.
        :param width: Width of the page.
        :param margin: Margin size.
        :return: A list of elements to be added to the PDF.
        """
        story = []
        story.append(Paragraph("Resumo dos Erros", self.styles['bold']))
        story.append(Spacer(1, 12))

        # Create a copy of the DataFrame and reset the index
        df_copy = self.failures_df.copy().reset_index()
        df_copy.columns = [
            'Nome',
            'Status',
            'Categoria do Teste',
            'Tipo de erro',
            'Detalhes do erro (100 caracteres)',
            'JobId',
        ]

        df_copy = df_copy.drop('Detalhes do erro (100 caracteres)', axis=1)

        # Prepare the detailed data for the table
        detailed_tests_data = [[Paragraph(str(value), self.styles['normal']) for value in df_copy.columns.tolist()]] 
        detailed_tests_data.extend(
            [[Paragraph(str(value), self.styles['normal']) for value in row] for row in df_copy.values.tolist()]
        )

        # Calculate available width after applying margins
        available_width = self.dim['width'] - 2 * self.dim['margin']  
        proportions = [0.3, 0.15, 0.15, 0.15, 0.2, 0.1]  

        # Calculate column widths based on the available width
        col_widths = [available_width * p for p in proportions]

        # Create the table
        detailed_table = Table(detailed_tests_data, colWidths=col_widths)
        detailed_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),  
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),  
        ]))
        story.append(detailed_table)
        story.append(Spacer(1, 24))

        return story

    def create_graphs(self):
        img_width = 500
        img_height = 250

        graph_files = {'error_distribution_pie':self.plotter.error_distribution_pie_chart(), 
                       'category_errors_bar': self.plotter.plot_category_errors_bar(),
                       'failures_passed_rate': self.plotter.categories_failures_passed_rate(),
                       }
        
        story = []
        story.append(Spacer(1, 12))

        # Add a title to the PDF
        story.append(Paragraph("Visualização de dados", self.styles['bold']))
        story.append(Spacer(1, 12))

        # Add the bar chart and aligning
        category_img = Image(graph_files['category_errors_bar'], width=img_width, height=img_height)
        category_img.hAlign = 'CENTER'

        # Add the pie chart and aligning
        error_dist_image = Image(graph_files['error_distribution_pie'], width=500, height=250)
        error_dist_image.hAlign = 'CENTER'
        
        # Add the pass/fail rate bar chart and aligning
        failure_passed_img = Image(graph_files['failures_passed_rate'], width=500, height=250)
        failure_passed_img.hAlign = 'CENTER'

        # Appending graphs to pdf
        story.append(category_img) 
        story.append(Spacer(1, 24))
        story.append(error_dist_image)  
        story.append(Spacer(1, 24))
        story.append(failure_passed_img)  
        story.append(Spacer(1, 24))

        return story


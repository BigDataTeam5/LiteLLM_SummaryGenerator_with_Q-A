import os
import csv
import io
import fitz  # PyMuPDF (for reading PDF metadata)
import boto3
from dotenv import load_dotenv
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult
from fastapi import HTTPException

def extract_and_upload_pdf(pdf_path):
    """Extracts text, images, tables, and metadata from a PDF and uploads them directly to S3."""
    
    # Load environment variables
    load_dotenv()

    # AWS S3 Configuration
    session = boto3.Session(
        aws_access_key_id=os.getenv('AWS_SERVER_PUBLIC_KEY'),
        aws_secret_access_key=os.getenv('AWS_SERVER_SECRET_KEY'),
    )
    s3 = session.client('s3')
    bucket_name = os.getenv('AWS_BUCKET_NAME')

    # Define base S3 path for structured storage
    s3_base_dir = "pdf_processing_pipeline/pdf_enterprise_pipeline"

    # Azure Credentials
    endpoint = os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT")
    key = os.getenv("AZURE_FORM_RECOGNIZER_KEY")


    # Initialize Azure Document Intelligence Client
    document_intelligence_client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))

    # Analyze Document
    with open(pdf_path, "rb") as f:
        poller = document_intelligence_client.begin_analyze_document("prebuilt-layout", body=f, output=["figures"])

    result: AnalyzeResult = poller.result()
    operation_id = poller.details["operation_id"]

    # -------- Upload Images Directly to S3 --------
    if result.figures:
        for figure in result.figures:
            if figure.id:
                s3_path = f"{s3_base_dir}/images/{figure.id}.png"

                response = document_intelligence_client.get_analyze_result_figure(
                    model_id=result.model_id, result_id=operation_id, figure_id=figure.id
                )

                # Convert generator response to bytes
                image_bytes = b"".join(response)

                # Upload image directly to S3
                s3.put_object(Bucket=bucket_name, Key=s3_path, Body=image_bytes)
                print(f"✅ Uploaded Image: s3://{bucket_name}/{s3_path}")
    else:
        print("❌ No figures found.")

    # -------- Upload Text Directly to S3 --------
    text_content = io.StringIO()

    if result.styles and any([style.is_handwritten for style in result.styles]):
        text_content.write("Document contains handwritten content\n")
    else:
        text_content.write("Document does not contain handwritten content\n")

    for page in result.pages:
        text_content.write(f"\n---- Page #{page.page_number} ----\n")
        text_content.write(f"Dimensions: Width {page.width}, Height {page.height}, Unit: {page.unit}\n")

        if page.lines:
            for line_idx, line in enumerate(page.lines):
                text_content.write(f"... Line #{line_idx}: '{line.content}'\n")

    # Upload text content to S3
    s3_path_text = f"{s3_base_dir}/text/extracted_text.txt"
    s3.put_object(Bucket=bucket_name, Key=s3_path_text, Body=text_content.getvalue())
    print(f"✅ Uploaded Extracted Text: s3://{bucket_name}/{s3_path_text}")

    # -------- Upload Tables Directly to S3 (CSV Format) --------
    if result.tables:
        print(f"\n---- Extracted {len(result.tables)} Tables ----")

        for table_idx, table in enumerate(result.tables):
            table_buffer = io.StringIO()
            writer = csv.writer(table_buffer)

            # Sort cells by row & column order
            table.cells.sort(key=lambda cell: (cell.row_index, cell.column_index))

            # Create an empty matrix for the table
            table_matrix = [["" for _ in range(table.column_count)] for _ in range(table.row_count)]

            # Fill matrix with cell data
            for cell in table.cells:
                table_matrix[cell.row_index][cell.column_index] = cell.content

            # Write table to CSV format in-memory
            writer.writerows(table_matrix)

            # Define S3 Path Before Uploading
            s3_path_table = f"{s3_base_dir}/tables/table_{table_idx}.csv"

            # Upload CSV file directly to S3
            s3.put_object(Bucket=bucket_name, Key=s3_path_table, Body=table_buffer.getvalue())
            print(f"✅ Uploaded Table {table_idx}: s3://{bucket_name}/{s3_path_table}")

    # -------- Upload Metadata Directly to S3 --------
    metadata_buffer = io.StringIO()
    metadata_buffer.write("📄 Document Metadata\n")
    metadata_buffer.write("----------------------------\n")
    metadata_buffer.write(f"Total Pages: {len(result.pages)}\n")
    metadata_buffer.write(f"Total Figures: {len(result.figures) if result.figures else 0}\n")
    metadata_buffer.write(f"Total Tables: {len(result.tables) if result.tables else 0}\n")
    metadata_buffer.write(f"Total Paragraphs: {len(result.paragraphs) if result.paragraphs else 0}\n")

    # Define S3 Path Before Uploading
    s3_path_metadata = f"{s3_base_dir}/others/metadata.txt"

    # Upload metadata directly to S3
    s3.put_object(Bucket=bucket_name, Key=s3_path_metadata, Body=metadata_buffer.getvalue())
    print(f"✅ Uploaded Metadata: s3://{bucket_name}/{s3_path_metadata}")

    print("\n✅✅✅ Extraction & Upload Completed Successfully! ✅✅✅")


# # Example Usage:
# pdf_path = "africas_manufacturing_puzzle-compressed.pdf"  # Replace with actual PDF path
# extract_and_upload_pdf(pdf_path)
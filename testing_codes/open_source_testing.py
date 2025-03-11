import os
import fitz  # PyMuPDF
import camelot
import requests
from dotenv import load_dotenv
import shutil

# Load environment variables
load_dotenv()

def download_pdf(url, output_path):
    """Download PDF from a URL and save to local storage."""
    response = requests.get(url)
    if response.status_code == 200:
        with open(output_path, "wb") as pdf_file:
            pdf_file.write(response.content)
        return f"PDF downloaded successfully: {output_path}"
    else:
        raise Exception(f"Failed to download PDF. Status code: {response.status_code}")

def extract_text_from_pdf(file_path, output_folder):
    """Extract text from PDF and save locally."""
    logs = []
    with fitz.open(file_path) as pdf_document:
        for page_num in range(len(pdf_document)):
            page_folder = os.path.join(output_folder, f"page_{page_num + 1}")
            os.makedirs(page_folder, exist_ok=True)
            text = pdf_document[page_num].get_text()
            text_filename = os.path.join(page_folder, "text.txt")
            with open(text_filename, "w", encoding="utf-8") as text_file:
                text_file.write(text)
            logs.append(f"Extracted text to {text_filename}")
    return logs

def extract_images_from_pdf(file_path, output_folder):
    """Extract images from PDF and save locally."""
    logs = []
    pdf_document = fitz.open(file_path)
    for page_num in range(len(pdf_document)):
        page_folder = os.path.join(output_folder, f"page_{page_num + 1}")
        os.makedirs(page_folder, exist_ok=True)
        page = pdf_document[page_num]
        image_list = page.get_images(full=True)
        for img_index, img in enumerate(image_list):
            xref = img[0]
            base_image = pdf_document.extract_image(xref)
            if base_image is None or "image" not in base_image:
                continue
            image_bytes = base_image["image"]
            image_ext = base_image["ext"]
            image_filename = os.path.join(page_folder, f"img_{img_index + 1}.{image_ext}")
            with open(image_filename, "wb") as img_file:
                img_file.write(image_bytes)
            logs.append(f"Extracted image to {image_filename}")
    return logs

def extract_tables_from_pdf(file_path, output_folder):
    """Extract tables from PDF and save locally."""
    logs = []
    tables = camelot.read_pdf(file_path, pages='all', flavor='stream')
    for table in tables:
        if table.parsing_report['accuracy'] >= 80:
            page_folder = os.path.join(output_folder, f"page_{table.page}")
            os.makedirs(page_folder, exist_ok=True)
            table_filename = os.path.join(page_folder, f"table_{table.page}.csv")
            table.to_csv(table_filename)
            logs.append(f"Extracted table to {table_filename}")
    return logs

def extract_lists_from_pdf(file_path, output_folder):
    """Extract lists from PDF and save locally."""
    logs = []
    with fitz.open(file_path) as pdf_document:
        for page_num in range(len(pdf_document)):
            page_folder = os.path.join(output_folder, f"page_{page_num + 1}")
            os.makedirs(page_folder, exist_ok=True)
            page = pdf_document[page_num]
            text = page.get_text()
            list_lines = [line.strip() for line in text.splitlines() if line.strip().startswith(('-', '*', '•', '○'))]
            if list_lines:
                list_filename = os.path.join(page_folder, "lists.txt")
                with open(list_filename, "w", encoding="utf-8") as list_file:
                    list_file.write("\n".join(list_lines))
                logs.append(f"Extracted lists to {list_filename}")
    return logs

def extract_all_from_pdf(file_path, output_folder):
    """Extract all data from a PDF and save locally."""
    logs = []
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    logs += extract_text_from_pdf(file_path, output_folder)
    logs += extract_images_from_pdf(file_path, output_folder)
    logs += extract_tables_from_pdf(file_path, output_folder)
    logs += extract_lists_from_pdf(file_path, output_folder)
    # return logs

def cleanup_files(file_path, output_folder):
    """Cleanup downloaded PDF and extracted files."""
    if os.path.exists(file_path):
        os.remove(file_path)
        print(f"Deleted file: {file_path}")
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
        print(f"Deleted folder: {output_folder}")

if __name__ == "__main__":
    # Download PDF from URL
    pdf_url = "https://arxiv.org/pdf/2408.09869"
    pdf_output_path = "dummy.pdf"
    print(download_pdf(pdf_url, pdf_output_path))

    # Extract all data from PDF
    output_folder = "pdf_data"
    print(extract_all_from_pdf(pdf_output_path, output_folder))

    # Cleanup files
    # cleanup_files(pdf_output_path, output_folder)
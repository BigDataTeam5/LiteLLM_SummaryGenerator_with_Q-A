import os
import requests
import boto3
from bs4 import BeautifulSoup
from io import BytesIO
from dotenv import load_dotenv

# ✅ Load environment variables
load_dotenv()

# ✅ AWS Configuration (Consistent with PDF Processing)
session = boto3.Session(
    aws_access_key_id=os.getenv('AWS_SERVER_PUBLIC_KEY'),
    aws_secret_access_key=os.getenv('AWS_SERVER_SECRET_KEY'),
)
s3 = session.client('s3')
bucket_name = os.getenv('AWS_BUCKET_NAME')
aws_region = os.getenv('AWS_REGION')  # e.g., 'us-east-1'

# ✅ List of disallowed file extensions
DISALLOWED_EXTENSIONS = [".pdf", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".zip", ".rar"]

# ✅ S3 Upload Function (Consistent with PDF Processing)
def upload_file_to_s3(file_content, s3_path, content_type="text/plain"):
    try:
        s3.put_object(
            Bucket=bucket_name,
            Key=s3_path,
            Body=file_content,
            ContentType=content_type,
        )
        s3_url = f"https://{bucket_name}.s3.{aws_region}.amazonaws.com/{s3_path}"
        print(f"Uploaded to S3: {s3_url}")
        return s3_url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None

# ✅ URL Validation
def is_valid_url(url):
    if not url.startswith(("http://", "https://")):
        print("Invalid URL. Please include http:// or https://.")
        return False

    if any(url.lower().endswith(ext) for ext in DISALLOWED_EXTENSIONS):
        print(f"URL points to a disallowed file type ({url.split('.')[-1]}).")
        return False

    return True

# ✅ Scrape Visual Data (Images & Tables)
def scrape_visual_data(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # ✅ Scrape & Upload Images
    img_tags = soup.find_all("img")
    images = []
    for idx, img_tag in enumerate(img_tags):
        img_url = img_tag.get("src")
        if not img_url:
            continue
        img_url = requests.compat.urljoin(url, img_url)

        try:
            img_data = requests.get(img_url).content
            s3_path = f"scraped_data/scraped_os_data/images/image_{idx + 1}.jpg"
            upload_url = upload_file_to_s3(img_data, s3_path, "image/jpeg")
            if upload_url:
                images.append(upload_url)
        except Exception as e:
            print(f"Failed to download image {img_url}: {e}")

    # ✅ Scrape & Upload Tables
    tables = []
    table_text = ""
    for table_idx, table in enumerate(soup.find_all("table"), start=1):
        table_data = []
        for row in table.find_all("tr"):
            row_data = [cell.get_text(strip=True) for cell in row.find_all(["td", "th"])]
            table_data.append(row_data)
        tables.append(table_data)

        # Convert table to string format
        table_text += f"Table {table_idx}:\n"
        for row in table_data:
            table_text += " | ".join(row) + "\n"
        table_text += "\n"

    # ✅ Upload table data to S3
    table_s3_path = "scraped_data/scraped_os_data/tables.txt"
    upload_file_to_s3(table_text.encode("utf-8"), table_s3_path, "text/plain")

    return {"images": images, "tables": tables, "tables_s3_url": table_s3_path}

# ✅ Scrape Text Data & Images, Store as Markdown
def scrape_text_data_with_images(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    # ✅ Remove script and style elements
    for script_or_style in soup(["script", "style"]):
        script_or_style.extract()

    # ✅ Extract all image references for Markdown
    img_tags = soup.find_all("img")
    image_markdown = []
    for idx, img_tag in enumerate(img_tags):
        img_url = img_tag.get("src")
        alt_text = img_tag.get("alt", f"Image {idx + 1}")
        if img_url:
            img_url = requests.compat.urljoin(url, img_url)
            image_markdown.append(f"![{alt_text}]({img_url})")

    # ✅ Get visible text
    text = soup.get_text()
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    cleaned_text = "\n".join(chunk for chunk in chunks if chunk)

    # ✅ Append image references to text
    markdown_content = f"{cleaned_text}\n\n## Images\n\n" + "\n\n".join(image_markdown)

    # ✅ Upload Markdown to S3
    markdown_s3_path = "scraped_data/scraped_os_data/scraped_content.md"
    upload_file_to_s3(markdown_content.encode("utf-8"), markdown_s3_path, "text/markdown")

    return markdown_s3_path

# ✅ Convert Scraped Data to Final Markdown
def convert_to_markdown(data):
    markdown_content = "# Extracted Web Content\n\n"

    # ✅ Add Images
    markdown_content += "## Images\n\n"
    for idx, image in enumerate(data["images"], start=1):
        markdown_content += f"![Image {idx}]({image})\n\n"

    # ✅ Add Tables
    markdown_content += "## Tables\n\n"
    for idx, table in enumerate(data["tables"], start=1):
        markdown_content += f"### Table {idx}\n\n"
        for row in table:
            markdown_content += "| " + " | ".join(row) + " |\n"
        markdown_content += "\n"

    # ✅ Upload Final Markdown
    markdown_s3_path = "scraped_data/scraped_os_data/final_scraped_content.md"
    upload_file_to_s3(markdown_content.encode("utf-8"), markdown_s3_path, "text/markdown")
    
    return markdown_s3_path

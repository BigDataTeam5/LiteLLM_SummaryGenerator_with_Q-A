import os
import requests
import boto3
from apify_client import ApifyClient
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from WebScraping_Extraction_and_Markdown_Generation.OSWebScrap import upload_file_to_s3

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

# ✅ Replace with your Apify API token
APIFY_TOKEN = os.getenv('APIFY_TOKEN')
if not APIFY_TOKEN:
    raise ValueError("Apify API token is missing. Please set the APIFY_TOKEN environment variable.")

# ✅ List of disallowed file extensions
DISALLOWED_EXTENSIONS = [".pdf", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".zip", ".rar"]

# ✅ Initialize FastAPI App
app = FastAPI()

# ✅ Scrape Request Model
class ScrapeRequest(BaseModel):
    url: str

# ✅ URL Validation
def is_valid_url(url):
    if not url.startswith(("http://", "https://")):
        return False
    if any(url.lower().endswith(ext) for ext in DISALLOWED_EXTENSIONS):
        return False
    return True

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
        print(f"✅ Uploaded to S3: {s3_url}")
        return s3_url
    except Exception as e:
        print(f"❌ Error uploading to S3: {e}")
        return None

# ✅ Download & Upload Images to S3
def save_and_upload_images(image_urls):
    s3_image_urls = []
    for idx, url in enumerate(image_urls):
        try:
            response = requests.get(url)
            response.raise_for_status()
            file_name = f"image_{idx + 1}.jpg"
            s3_path = f"scraped_data/scraped_en_data/images/{file_name}"
            upload_url = upload_file_to_s3(response.content, s3_path, "image/jpeg")
            if upload_url:
                s3_image_urls.append(upload_url)
        except Exception as e:
            print(f"❌ Failed to download/upload image {url}: {e}")
    return s3_image_urls

# ✅ Generate Markdown Content & Upload to S3
def generate_and_upload_markdown(text_content, image_urls):
    markdown_content = "# Extracted Webpage Data\n\n## Page Content\n\n" + text_content + "\n\n"
    if image_urls:
        markdown_content += "## Extracted Images\n\n"
        for idx, url in enumerate(image_urls):
            markdown_content += f"![Image {idx + 1}]({url})\n\n"

    # ✅ Upload to S3
    markdown_s3_path = "scraped_data/scraped_en_data/extracted_content.md"
    upload_file_to_s3(markdown_content.encode("utf-8"), markdown_s3_path, "text/markdown")
    
    return markdown_s3_path

# ✅ FastAPI Endpoint for Enterprise Web Scraping
@app.post("/enscrape")
def scrape_webpage(request: ScrapeRequest):
    """Scrape a webpage using Apify and upload the results to S3."""
    if not is_valid_url(request.url):
        raise HTTPException(status_code=400, detail="Invalid URL or unsupported file type.")

    # ✅ Apify actor configuration
    actor_id = "apify/puppeteer-scraper"
    input_data = {
        "startUrls": [{"url": request.url}],
        "maxConcurrency": 10,
        "maxPagesPerCrawl": 5,
        "pageFunction": """async ({ page, request }) => {
            try {
                await page.waitForSelector('img');
                const images = await page.$$eval('img', imgs => imgs.map(img => img.src || img.getAttribute('ng-src')));
                const validImages = [...new Set(images)].filter(url => url && url.startsWith('http'));
                const textContent = await page.evaluate(() => document.body.innerText);
                return { url: request.url, title: await page.title(), images: validImages, text: textContent };
            } catch (error) {
                return { url: request.url, error: error.message };
            }
        }""",
    }

    try:
        # ✅ Initialize Apify client
        client = ApifyClient(APIFY_TOKEN)

        # ✅ Run the Apify actor
        run = client.actor(actor_id).call(run_input=input_data)

        # ✅ Fetch the results
        dataset_id = run["defaultDatasetId"]
        items = client.dataset(dataset_id).list_items().items

        # ✅ Process the results
        for item in items:
            images = item.get("images", [])
            text = item.get("text", "")
            s3_image_urls = save_and_upload_images(images)
            md_s3_url = generate_and_upload_markdown(text, s3_image_urls)
            return {"markdown_s3_url": md_s3_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"❌ An error occurred: {str(e)}")

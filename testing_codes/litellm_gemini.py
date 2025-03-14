import os
import base64
import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path
import litellm
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure LiteLLM with your Gemini API key
litellm.api_key = os.getenv("gemini_api_key")

def encode_image_to_base64(image_path: str) -> str:
    """Convert an image file to base64 encoding."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def read_text_file(file_path: str) -> str:
    """Read and return the contents of a text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        print(f"Error reading text file {file_path}: {e}")
        return f"[Error reading file: {file_path}]"

def read_csv_file(file_path: str) -> str:
    """Read a CSV file and convert it to a markdown table string."""
    try:
        df = pd.read_csv(file_path)
        return f"Table from {Path(file_path).name}:\n{df.to_markdown(index=False)}\n"
    except Exception as e:
        print(f"Error reading CSV file {file_path}: {e}")
        return f"[Error reading CSV file: {file_path}]"

def collect_content_from_folder(folder_path: str) -> Dict[str, Any]:
    """
    Collect all content from the output folder.
    Returns a dictionary with text content and image paths.
    """
    result = {
        "text_content": "",
        "image_paths": []
    }
    
    # Get all files recursively
    for root, _, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_extension = Path(file).suffix.lower()
            
            if file_extension == '.txt':
                content = read_text_file(file_path)
                result["text_content"] += f"\n--- Content from {file} ---\n{content}\n"
            elif file_extension == '.csv':
                table_content = read_csv_file(file_path)
                result["text_content"] += f"\n{table_content}\n"
            elif file_extension in ['.png', '.jpg', '.jpeg', '.gif']:
                result["image_paths"].append(file_path)
    
    return result

def create_gemini_summary(folder_path: str, max_images: int = 5) -> str:
    """
    Generate a summary of PDF content using Gemini.
    
    Args:
        folder_path: Path to the folder containing parsed PDF content
        max_images: Maximum number of images to include (Gemini has input limits)
        
    Returns:
        A string containing the summary
    """
    try:
        # Collect content
        content = collect_content_from_folder(folder_path)
        
        # Prepare the prompt
        prompt_text = f"""
        I need you to create a comprehensive summary of the following document content.
        
        The content includes text, tables, and images extracted from a PDF.
        Please analyze all the provided information and create a well-structured summary that:
        
        1. Identifies the main topic and purpose of the document
        2. Summarizes the key points and findings
        3. Highlights important data from tables
        4. Describes what's shown in the images
        5. Organizes the information in a logical flow
        
        Here's the extracted content:
        
        {content["text_content"]}
        """
        
        # Prepare the messages with text and images
        messages = [{"role": "user", "content": prompt_text}]
        
        # Add images if available (limited to max_images)
        image_paths = content["image_paths"][:max_images]  # Limit number of images
        
        if image_paths:
            # For multimodal input with images
            image_parts = []
            for img_path in image_paths:
                try:
                    base64_image = encode_image_to_base64(img_path)
                    image_parts.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    })
                except Exception as e:
                    print(f"Error encoding image {img_path}: {e}")
            
            # Add image parts to the message
            if image_parts:
                messages = [
                    {
                        "role": "user", 
                        "content": [
                            {"type": "text", "text": prompt_text},
                            *image_parts
                        ]
                    }
                ]
        
        # Call Gemini model using LiteLLM - use the newer 1.5 models
        # Use gemini-1.5-flash for both text and image inputs
        response = litellm.completion(
            model="gemini/gemini-1.5-flash",  # Updated to use newer model
            messages=messages,
            temperature=0.3,
            max_tokens=4000
        )
        
        # Extract and return the summary
        if response and response.choices and response.choices[0].message.content:
            return response.choices[0].message.content
        else:
            return "Error: No response generated from Gemini."
    
    except Exception as e:
        return f"Error generating summary: {str(e)}"

def summarize_pdf_content(job_folder_path: str) -> str:
    """
    Main function to summarize PDF content.
    
    Args:
        job_folder_path: Path to the specific job folder containing the parsed PDF
        
    Returns:
        The generated summary
    """
    print(f"Generating summary for content in: {job_folder_path}")
    summary = create_gemini_summary(job_folder_path)
    
    # Save the summary to a file
    summary_path = os.path.join(job_folder_path, "gemini_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)
    
    print(f"Summary saved to: {summary_path}")
    return summary

if __name__ == "__main__":
    # Example usage:
    # Replace with the path to your PDF job folder
    output_folder = "../output"
    pdf_name = "arxiv_paper"  # The PDF filename without extension
    job_folder = os.path.join(output_folder, pdf_name)
    
    if os.path.exists(job_folder):
        summary = summarize_pdf_content(job_folder)
        print("\nSummary Preview:")
        print(summary[:500] + "..." if len(summary) > 500 else summary)
    else:
        print(f"Job folder not found: {job_folder}")
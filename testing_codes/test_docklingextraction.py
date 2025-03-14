import logging
import time
import argparse
from pathlib import Path
from docling_core.types.doc import ImageRefMode, PictureItem, TableItem
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

# Constants
IMAGE_RESOLUTION_SCALE = 2.0

def process_pdf_locally(pdf_path, service_type="test"):
    """
    Process a PDF file and save outputs locally without S3 uploads
    
    Args:
        pdf_path: Path to the PDF file
        service_type: Service type identifier for folder naming
    """
    logging.basicConfig(level=logging.INFO)
    logging.info(f"Processing PDF: {pdf_path}")

    input_doc_path = Path(pdf_path)
    output_dir = Path(f"output/{Path(pdf_path).stem}")

    # Configure pipeline options
    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale = IMAGE_RESOLUTION_SCALE
    pipeline_options.generate_page_images = True
    pipeline_options.generate_picture_images = True

    doc_converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    start_time = time.time()
    # Convert the document
    logging.info("Converting document...")
    conv_res = doc_converter.convert(input_doc_path)

    doc_filename = conv_res.input.file.stem
    # Define job-specific folder based on PDF filename and service type
    job_folder = f"{doc_filename}-{service_type}"

    # Create a local output directory for the job
    output_dir = output_dir / job_folder
    output_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Saving outputs to: {output_dir}")

    # Save page images inside the job-specific folder
    logging.info("Saving page images...")
    for page_no, page in conv_res.document.pages.items():
        page_image_filename = output_dir / f"{doc_filename}-{page_no}.png"
        with page_image_filename.open("wb") as fp:
            page.image.pil_image.save(fp, format="PNG")
        logging.info(f"Saved page image: {page_image_filename}")

    # Save images of tables and figures inside the job-specific folder
    table_counter = 0
    picture_counter = 0
    logging.info("Saving tables and figures...")
    for element, _level in conv_res.document.iterate_items():
        if isinstance(element, TableItem):
            table_counter += 1
            element_image_filename = output_dir / f"{doc_filename}-table-{table_counter}.png"
            with element_image_filename.open("wb") as fp:
                element.get_image(conv_res.document).save(fp, "PNG")
            logging.info(f"Saved table image: {element_image_filename}")

        if isinstance(element, PictureItem):
            picture_counter += 1
            element_image_filename = output_dir / f"{doc_filename}-picture-{picture_counter}.png"
            with element_image_filename.open("wb") as fp:
                element.get_image(conv_res.document).save(fp, "PNG")
            logging.info(f"Saved picture image: {element_image_filename}")

    # Save markdown with embedded images inside the job-specific folder
    logging.info("Saving markdown files...")
    md_filename_embedded = output_dir / f"{doc_filename}-with-images.md"
    conv_res.document.save_as_markdown(md_filename_embedded, image_mode=ImageRefMode.EMBEDDED)
    logging.info(f"Saved markdown with embedded images: {md_filename_embedded}")

    # Save markdown with externally referenced images inside the job-specific folder
    md_filename_referenced = output_dir / f"{doc_filename}-with-image-refs.md"
    conv_res.document.save_as_markdown(md_filename_referenced, image_mode=ImageRefMode.REFERENCED)
    logging.info(f"Saved markdown with image references: {md_filename_referenced}")

    end_time = time.time() - start_time
    logging.info(f"Document converted and saved in {end_time:.2f} seconds.")
    logging.info(f"Output files stored in: {output_dir}")
    
    return output_dir

def main():
    """
    Main function to run the test with command line arguments
    """
    parser = argparse.ArgumentParser(description="Process PDF locally without S3 uploads")
    parser.add_argument("pdf_path", help="Path to the PDF file to process")
    parser.add_argument("--service", default="Open Source", help="Service type identifier (default: test)")
    args = parser.parse_args()
    
    output_dir = process_pdf_locally(args.pdf_path, args.service)
    print(f"\nProcessing complete! Check results in: {output_dir}")

if __name__ == "__main__":
    main()

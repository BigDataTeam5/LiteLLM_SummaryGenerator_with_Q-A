This project enhances Assignment 1 by developing a Streamlit application that integrates Large Language Models (LLMs) via FastAPI and LiteLLM for API management. The application allows users to summarize and query uploaded PDF documents.

Assignment Objectives

Develop a Streamlit web application with:

The ability to select and load previously parsed PDFs or upload new ones.

Integration with GPT-4o, Gemini Flash, DeepSeek, Claude, and Grok via LiteLLM.

Functionality to summarize documents and answer questions based on PDF content.

Integrate FastAPI to handle backend API interactions:

Endpoints:

/select_pdfcontent - Retrieve previously parsed PDFs.

/upload_pdf - Upload and parse new PDF files.

/summarize - Generate summaries of PDF content.

/ask_question - Process user questions and return LLM-generated answers.

Implement Redis streams for inter-service communication.

Implement LiteLLM API management:

Handle LLM API interactions efficiently.

Track token usage and pricing.

Implement error handling and logging.

Deploy the system using Docker Compose on a cloud platform.

Functional Requirements

Front-End (Streamlit)

Select preferred LLM model (e.g., GPT-4o, Gemini Flash, DeepSeek, Claude, Grok).

Load previously parsed PDF content or upload new PDFs.

Provide text input for user queries.

Summarize document content with a button-triggered function.

Display summaries and answers clearly.

Back-End (FastAPI)

Implement REST API endpoints for handling PDF selection, upload, summarization, and Q&A.

Ensure structured JSON responses.

Use Redis streams for efficient inter-service communication.

LiteLLM Integration

Manage API interactions for various LLM models.

Document model usage and track token-based pricing.

Implement robust error handling and logging.

Deployment

Docker Compose-based deployment.

Host services on cloud infrastructure.

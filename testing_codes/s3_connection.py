# test_/test_aws_s3.py
import boto3
import pytest
import os
from dotenv import load_dotenv
from botocore.exceptions import ClientError

@pytest.fixture(scope="module")
def s3_client():
    """Create an S3 client using credentials from .env file."""
    # Load environment variables from .env file
    load_dotenv()
    
    # Access AWS credentials from environment variables
    aws_access_key = os.getenv("AWS_SERVER_PUBLIC_KEY")
    aws_secret_key = os.getenv("AWS_SERVER_SECRET_KEY")
    aws_region = os.getenv("AWS_REGION")
    
    # Create S3 client
    client = boto3.client(
        "s3",
        region_name=aws_region,
        aws_access_key_id=aws_access_key,
        aws_secret_access_key=aws_secret_key
    )
    
    return client


def test_s3_connection(s3_client):
    """Test that we can connect to S3 and list buckets."""
    try:
        # Attempt to list buckets
        response = s3_client.list_buckets()
        assert "Buckets" in response
        assert isinstance(response["Buckets"], list)
        print(f"Successfully connected to S3. Found {len(response['Buckets'])} buckets.")
    except ClientError as e:
        pytest.fail(f"S3 connection failed: {str(e)}")

def test_bucket_exists(s3_client):
    """Test that our target bucket exists."""
    bucket_name = os.getenv("AWS_BUCKET_NAME")
    try:
        # Check if bucket exists by trying to access its properties
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"Bucket '{bucket_name}' exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            pytest.fail(f"Bucket '{bucket_name}' does not exist")
        else:
            pytest.fail(f"Error checking bucket: {str(e)}")

def test_s3_operations(s3_client):
    """Test basic S3 operations (put, get, delete)."""
    bucket_name = os.getenv("AWS_BUCKET_NAME")
    test_key = "test/test_file.txt"
    test_data = b"This is a test file for S3 connection verification."
    
    try:
        # Upload test file
        s3_client.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_data
        )
        print(f"Successfully uploaded test file to {bucket_name}/{test_key}")
        
        # Get the file and verify content
        response = s3_client.get_object(
            Bucket=bucket_name,
            Key=test_key
        )
        content = response['Body'].read()
        assert content == test_data
        print("Successfully retrieved and verified file content.")
        
        # Delete the test file
        s3_client.delete_object(
            Bucket=bucket_name,
            Key=test_key
        )
        print(f"Successfully deleted test file from {bucket_name}/{test_key}")
        
    except ClientError as e:
        pytest.fail(f"S3 operation failed: {str(e)}")
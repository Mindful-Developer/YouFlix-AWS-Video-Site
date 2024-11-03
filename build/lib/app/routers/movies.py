from fastapi import APIRouter, Depends, UploadFile
from app.utils import aws_dynamodb, aws_s3


router = APIRouter()

@router.post("/movies")
def add_movie(file: UploadFile, metadata: dict):
    # Logic to upload movie to S3 and store metadata in DynamoDB
    pass
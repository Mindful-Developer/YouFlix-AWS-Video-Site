import boto3
from botocore.exceptions import ClientError

from config import AWS_S3_BUCKET


s3_client = boto3.client("s3")


async def upload_movie(file_obj, object_name):
    try:
        s3_client.upload_fileobj(file_obj, AWS_S3_BUCKET, object_name)
    except ClientError as e:
        raise e


def delete_movie(object_name):
    try:
        s3_client.delete_object(Bucket=AWS_S3_BUCKET, Key=object_name)
    except ClientError as e:
        raise e


def get_presigned_url(object_name, expiration=3600):
    try:
        response = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": AWS_S3_BUCKET, "Key": object_name},
            ExpiresIn=expiration,
        )
    except ClientError as e:
        return None
    return response

import boto3


s3_client = boto3.client('s3')


def upload_movie(file_obj, bucket_name, object_name):
    s3_client.upload_fileobj(file_obj, bucket_name, object_name)


def download_movie(bucket_name, object_name):
    s3_client.download_file(bucket_name, object_name, 'local_filename')

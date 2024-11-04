import os
from app.utils.parameter_store import get_parameter


DATABASE_URL = get_parameter("/youflix/DATABASE_URL") + "/YouFlix"
AWS_REGION = get_parameter("/youflix/AWS_REGION")
AWS_S3_BUCKET = get_parameter("/youflix/AWS_S3_BUCKET")
DYNAMODB_TABLE = get_parameter("/youflix/DYNAMODB_TABLE")
SECRET_KEY = get_parameter("/youflix/SECRET_KEY")
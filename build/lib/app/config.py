import os
from app.utils.parameter_store import get_parameter


DATABASE_URL = os.getenv("DATABASE_URL") or get_parameter("DATABASE_URL")
AWS_REGION = os.getenv("AWS_REGION") or "us-east-1"
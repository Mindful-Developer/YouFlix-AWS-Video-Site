import boto3
import argparse
import time
import json
from botocore.exceptions import ClientError
from typing import Dict, Any

class AWSResourceManager:
    def __init__(self, profile: str = 'default', region: str = 'us-east-1'):
        """Initialize AWS session and clients"""
        session = boto3.Session(profile_name=profile, region_name=region)
        self.s3 = session.client('s3')
        self.dynamodb = session.client('dynamodb')
        self.rds = session.client('rds')
        self.ssm = session.client('ssm')
        self.iam = session.client('iam')
        self.elastic_beanstalk = session.client('elasticbeanstalk')
        self.ec2 = session.client('ec2')
        self.region = region

    def create_s3_bucket(self, bucket_name: str) -> Dict[str, Any]:
        """Create S3 bucket for movie storage"""
        try:
            if self.region == 'us-east-1':
                self.s3.create_bucket(Bucket=bucket_name)
            else:
                self.s3.create_bucket(
                    Bucket=bucket_name,
                    CreateBucketConfiguration={'LocationConstraint': self.region}
                )

            # Enable versioning
            self.s3.put_bucket_versioning(
                Bucket=bucket_name,
                VersioningConfiguration={'Status': 'Enabled'}
            )

            # Set private access
            self.s3.put_public_access_block(
                Bucket=bucket_name,
                PublicAccessBlockConfiguration={
                    'BlockPublicAcls': True,
                    'IgnorePublicAcls': True,
                    'BlockPublicPolicy': True,
                    'RestrictPublicBuckets': True
                }
            )

            print(f"✅ Created S3 bucket: {bucket_name}")
            return {"bucket_name": bucket_name}
        except ClientError as e:
            print(f"❌ Error creating S3 bucket: {e}")
            raise

    def create_dynamodb_tables(self, table_prefix: str) -> Dict[str, Any]:
        """Create DynamoDB tables for movies, comments, and ratings"""
        tables = {
            f"{table_prefix}-movies": {
                "KeySchema": [
                    {"AttributeName": "id", "KeyType": "HASH"}
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "genre", "AttributeType": "S"},
                    {"AttributeName": "rating", "AttributeType": "N"}
                ],
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "GenreIndex",
                        "KeySchema": [
                            {"AttributeName": "genre", "KeyType": "HASH"}
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    },
                    {
                        "IndexName": "RatingIndex",
                        "KeySchema": [
                            {"AttributeName": "rating", "KeyType": "HASH"}
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ],
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                }
            },
            f"{table_prefix}-comments": {
                "KeySchema": [
                    {"AttributeName": "id", "KeyType": "HASH"}
                ],
                "AttributeDefinitions": [
                    {"AttributeName": "id", "AttributeType": "S"},
                    {"AttributeName": "movie_id", "AttributeType": "S"}
                ],
                "GlobalSecondaryIndexes": [
                    {
                        "IndexName": "MovieIndex",
                        "KeySchema": [
                            {"AttributeName": "movie_id", "KeyType": "HASH"}
                        ],
                        "Projection": {"ProjectionType": "ALL"},
                        "ProvisionedThroughput": {
                            "ReadCapacityUnits": 5,
                            "WriteCapacityUnits": 5
                        }
                    }
                ],
                "ProvisionedThroughput": {
                    "ReadCapacityUnits": 5,
                    "WriteCapacityUnits": 5
                }
            }
        }

        created_tables = {}
        for table_name, table_config in tables.items():
            try:
                self.dynamodb.create_table(
                    TableName=table_name,
                    **table_config
                )
                print(f"✅ Created DynamoDB table: {table_name}")
                created_tables[table_name] = table_name
            except ClientError as e:
                if 'ResourceInUseException' in str(e):
                    print(f"⚠️ DynamoDB table {table_name} already exists")
                    created_tables[table_name] = table_name
                else:
                    print(f"❌ Error creating DynamoDB table {table_name}: {e}")
                    raise

        # Wait for tables to be created
        for table_name in tables.keys():
            self._wait_for_dynamodb_table(table_name)

        return created_tables

    def create_rds_instance(
            self,
            db_identifier: str,
            username: str,
            password: str
    ) -> Dict[str, Any]:
        """Create RDS SQL Server instance"""
        try:
            # First create a security group
            security_group_id = self._create_rds_security_group()

            print(f"⏳ Creating RDS instance {db_identifier}...")
            response = self.rds.create_db_instance(
                DBInstanceIdentifier=db_identifier,
                AllocatedStorage=20,
                DBInstanceClass='db.t3.micro',
                Engine='sqlserver-ex',
                MasterUsername=username,
                MasterUserPassword=password,
                VpcSecurityGroupIds=[security_group_id],
                PubliclyAccessible=True,
                MultiAZ=False,
                EngineVersion='15.00.4335.1.v1',
                AutoMinorVersionUpgrade=True,
                BackupRetentionPeriod=7,
                Port=1433,
                LicenseModel='license-included'
            )

            # Wait for the instance to be available
            print("⏳ Waiting for RDS instance to be available (this may take several minutes)...")
            waiter = self.rds.get_waiter('db_instance_available')
            waiter.wait(
                DBInstanceIdentifier=db_identifier,
                WaiterConfig={
                    'Delay': 30,
                    'MaxAttempts': 60
                }
            )

            # Get the endpoint
            instance = self.rds.describe_db_instances(
                DBInstanceIdentifier=db_identifier
            )['DBInstances'][0]
            endpoint = instance['Endpoint']['Address']
            port = instance['Endpoint']['Port']

            print(f"✅ Created RDS instance: {db_identifier}")
            return {
                "endpoint": endpoint,
                "port": port,
                "username": username
            }
        except ClientError as e:
            print(f"❌ Error creating RDS instance: {e}")
            raise

    def store_parameters(
            self,
            app_name: str,
            parameters: Dict[str, str]
    ) -> None:
        """Store parameters in AWS Systems Manager Parameter Store"""
        try:
            for key, value in parameters.items():
                param_name = f"/{app_name}/{key}"
                self.ssm.put_parameter(
                    Name=param_name,
                    Value=value,
                    Type='SecureString',
                    Overwrite=True
                )
            print("✅ Stored parameters in Parameter Store")
        except ClientError as e:
            print(f"❌ Error storing parameters: {e}")
            raise

    def create_elastic_beanstalk_app(
            self,
            app_name: str,
            environment_name: str
    ) -> Dict[str, Any]:
        """Create Elastic Beanstalk application and environment"""
        try:
            # Create application
            self.elastic_beanstalk.create_application(
                ApplicationName=app_name,
                Description='YouFlix video streaming application'
            )

            # Get available solution stacks
            solution_stacks = self.elastic_beanstalk.list_available_solution_stacks()
            python_stacks = [
                stack for stack in solution_stacks['SolutionStacks']
                if 'Python' in stack
            ]

            if not python_stacks:
                raise Exception("No Python solution stacks available")

            # Use the latest Python stack available
            solution_stack = python_stacks[0]
            print(f"Using solution stack: {solution_stack}")

            # Create environment
            response = self.elastic_beanstalk.create_environment(
                ApplicationName=app_name,
                EnvironmentName=environment_name,
                SolutionStackName=solution_stack,
                OptionSettings=[
                    {
                        'Namespace': 'aws:autoscaling:launchconfiguration',
                        'OptionName': 'InstanceType',
                        'Value': 't3.micro'
                    },
                    {
                        'Namespace': 'aws:autoscaling:asg',
                        'OptionName': 'MinSize',
                        'Value': '1'
                    },
                    {
                        'Namespace': 'aws:autoscaling:asg',
                        'OptionName': 'MaxSize',
                        'Value': '2'
                    }
                ]
            )

            print(f"✅ Created Elastic Beanstalk application: {app_name}")
            return {
                "application_name": app_name,
                "environment_name": environment_name,
                "environment_id": response['EnvironmentId']
            }
        except ClientError as e:
            print(f"❌ Error creating Elastic Beanstalk application: {e}")
            raise

    def _create_rds_security_group(self) -> str:
        """Create and configure security group for RDS"""
        try:
            # Get default VPC
            vpcs = self.ec2.describe_vpcs(
                Filters=[{'Name': 'isDefault', 'Values': ['true']}]
            )
            if not vpcs['Vpcs']:
                raise Exception("No default VPC found")
            vpc_id = vpcs['Vpcs'][0]['VpcId']

            # Create security group
            response = self.ec2.create_security_group(
                GroupName=f'youflix-rds-{int(time.time())}',
                Description='Security group for YouFlix RDS instance',
                VpcId=vpc_id
            )
            security_group_id = response['GroupId']

            # Add inbound rule for SQL Server
            self.ec2.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[
                    {
                        'IpProtocol': 'tcp',
                        'FromPort': 1433,
                        'ToPort': 1433,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }
                ]
            )

            print(f"✅ Created security group for RDS: {security_group_id}")
            return security_group_id

        except ClientError as e:
            print(f"❌ Error creating security group: {e}")
            raise

    def _wait_for_dynamodb_table(self, table_name: str) -> None:
        """Wait for DynamoDB table to be created"""
        print(f"⏳ Waiting for DynamoDB table {table_name} to be active...")
        waiter = self.dynamodb.get_waiter('table_exists')
        waiter.wait(
            TableName=table_name,
            WaiterConfig={'Delay': 5, 'MaxAttempts': 20}
        )


def main():
    parser = argparse.ArgumentParser(description='Set up AWS infrastructure for YouFlix')
    parser.add_argument('--profile', default='default', help='AWS profile to use')
    parser.add_argument('--region', default='us-east-1', help='AWS region to use')
    parser.add_argument('--app-name', required=True, help='Application name prefix for resources')
    args = parser.parse_args()

    # Initialize AWS resource manager
    aws = AWSResourceManager(args.profile, args.region)

    try:
        # Create S3 bucket
        s3_info = aws.create_s3_bucket(f"{args.app_name}-movies")

        # Create DynamoDB tables
        dynamodb_info = aws.create_dynamodb_tables(args.app_name)

        # Create RDS instance
        db_password = 'E+LqSg~^dhA2p>N['  # Should be generated securely
        rds_info = aws.create_rds_instance(
            f"{args.app_name}-db",
            "admin",
            db_password
        )

        # Store parameters
        parameters = {
            "DATABASE_URL": f"mssql+pymssql://{rds_info['username']}:{db_password}@{rds_info['endpoint']}:{rds_info['port']}",
            "AWS_S3_BUCKET": s3_info['bucket_name'],
            "DYNAMODB_TABLE": list(dynamodb_info.values())[0],  # Movies table
            "SECRET_KEY": "WvS29V^_/~R=gmw<",  # Should be generated securely
            "AWS_REGION": args.region
        }
        aws.store_parameters(args.app_name, parameters)

        # Create Elastic Beanstalk application
        eb_info = aws.create_elastic_beanstalk_app(
            args.app_name,
            f"{args.app_name}-env"
        )

        # Save configuration for reference
        config = {
            "s3": s3_info,
            "dynamodb": dynamodb_info,
            "rds": rds_info,
            "elastic_beanstalk": eb_info,
            "parameters": {k: f"/{args.app_name}/{k}" for k in parameters.keys()}
        }

        with open('aws_config.json', 'w') as f:
            json.dump(config, f, indent=2)

        print("\n✅ AWS infrastructure setup completed successfully!")
        print("📝 Configuration saved to aws_config.json")

        # Print important information
        print("\nImportant Information:")
        print(f"RDS Endpoint: {rds_info['endpoint']}")
        print(f"RDS Port: {rds_info['port']}")
        print(f"RDS Username: {rds_info['username']}")
        print("Note: After RDS is available, you'll need to:")
        print("1. Connect to the database using SQL Server Management Studio or similar tool")
        print("2. Create your database manually")
        print("3. Update the DATABASE_URL parameter in Parameter Store with the database name")

    except Exception as e:
        print(f"\n❌ Error during setup: {str(e)}")
        raise


if __name__ == "__main__":
    main()
import boto3
import argparse
import json
import time
from botocore.exceptions import ClientError
from typing import List
from concurrent.futures import ThreadPoolExecutor


class AWSResourceCleaner:
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

    def delete_s3_bucket(self, bucket_name: str) -> None:
        """Delete S3 bucket and all its contents"""
        try:
            # Delete all objects and versions
            paginator = self.s3.get_paginator('list_object_versions')

            print(f"🗑️ Deleting all objects from bucket {bucket_name}...")
            try:
                for page in paginator.paginate(Bucket=bucket_name):
                    versions = page.get('Versions', [])
                    delete_markers = page.get('DeleteMarkers', [])

                    objects_to_delete = []

                    for version in versions:
                        objects_to_delete.append({
                            'Key': version['Key'],
                            'VersionId': version['VersionId']
                        })

                    for marker in delete_markers:
                        objects_to_delete.append({
                            'Key': marker['Key'],
                            'VersionId': marker['VersionId']
                        })

                    if objects_to_delete:
                        self.s3.delete_objects(
                            Bucket=bucket_name,
                            Delete={'Objects': objects_to_delete}
                        )
            except ClientError as e:
                if e.response['Error']['Code'] != 'NoSuchBucket':
                    raise e

            # Delete the bucket
            print(f"🗑️ Deleting bucket {bucket_name}...")
            self.s3.delete_bucket(Bucket=bucket_name)
            print(f"✅ Deleted S3 bucket: {bucket_name}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchBucket':
                print(f"ℹ️ Bucket {bucket_name} does not exist")
            else:
                print(f"❌ Error deleting S3 bucket {bucket_name}: {e}")

    def delete_dynamodb_tables(self, table_names: List[str]) -> None:
        """Delete DynamoDB tables"""
        for table_name in table_names:
            try:
                print(f"🗑️ Deleting DynamoDB table {table_name}...")
                self.dynamodb.delete_table(TableName=table_name)
                self._wait_for_dynamodb_table_deletion(table_name)
                print(f"✅ Deleted DynamoDB table: {table_name}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"ℹ️ Table {table_name} does not exist")
                else:
                    print(f"❌ Error deleting DynamoDB table {table_name}: {e}")

    def delete_rds_instance(self, db_identifier: str) -> None:
        """Delete RDS instance"""
        try:
            print(f"🗑️ Deleting RDS instance {db_identifier}...")
            self.rds.delete_db_instance(
                DBInstanceIdentifier=db_identifier,
                SkipFinalSnapshot=True,
                DeleteAutomatedBackups=True
            )

            print("⏳ Waiting for RDS instance to be deleted (this may take several minutes)...")
            waiter = self.rds.get_waiter('db_instance_deleted')
            waiter.wait(
                DBInstanceIdentifier=db_identifier,
                WaiterConfig={'Delay': 30, 'MaxAttempts': 60}
            )
            print(f"✅ Deleted RDS instance: {db_identifier}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'DBInstanceNotFound':
                print(f"ℹ️ RDS instance {db_identifier} does not exist")
            else:
                print(f"❌ Error deleting RDS instance {db_identifier}: {e}")

    def delete_parameters(self, app_name: str) -> None:
        """Delete parameters from Parameter Store"""
        try:
            # Get all parameters for the application
            paginator = self.ssm.get_paginator('get_parameters_by_path')
            path = f"/{app_name}/"

            parameters_to_delete = []
            for page in paginator.paginate(Path=path):
                parameters_to_delete.extend([p['Name'] for p in page['Parameters']])

            if parameters_to_delete:
                print(f"🗑️ Deleting parameters for {app_name}...")
                # Delete parameters in batches of 10 (AWS limit)
                for i in range(0, len(parameters_to_delete), 10):
                    batch = parameters_to_delete[i:i + 10]
                    self.ssm.delete_parameters(Names=batch)
                print(f"✅ Deleted parameters for: {app_name}")
            else:
                print(f"ℹ️ No parameters found for {app_name}")

        except ClientError as e:
            print(f"❌ Error deleting parameters: {e}")

    def delete_elastic_beanstalk_app(self, app_name: str) -> None:
        """Delete Elastic Beanstalk application and all its environments"""
        try:
            # Get all environments for the application
            environments = self.elastic_beanstalk.describe_environments(
                ApplicationName=app_name
            )['Environments']

            # Delete each environment
            for env in environments:
                env_name = env['EnvironmentName']
                print(f"🗑️ Terminating Elastic Beanstalk environment {env_name}...")

                try:
                    self.elastic_beanstalk.terminate_environment(
                        EnvironmentName=env_name
                    )

                    print("⏳ Waiting for environment to terminate...")
                    waiter = self.elastic_beanstalk.get_waiter('environment_terminated')
                    waiter.wait(
                        EnvironmentNames=[env_name],
                        WaiterConfig={'Delay': 30, 'MaxAttempts': 40}
                    )
                except ClientError as e:
                    print(f"❌ Error terminating environment {env_name}: {e}")

            # Delete the application
            print(f"🗑️ Deleting Elastic Beanstalk application {app_name}...")
            self.elastic_beanstalk.delete_application(
                ApplicationName=app_name,
                TerminateEnvByForce=True
            )
            print(f"✅ Deleted Elastic Beanstalk application: {app_name}")

        except ClientError as e:
            if e.response['Error']['Code'] == 'ApplicationNotFoundException':
                print(f"ℹ️ Elastic Beanstalk application {app_name} does not exist")
            else:
                print(f"❌ Error deleting Elastic Beanstalk application: {e}")

    def delete_security_groups(self, group_prefix: str) -> None:
        """Delete security groups created for the application"""
        try:
            response = self.ec2.describe_security_groups(
                Filters=[{'Name': 'group-name', 'Values': [f'{group_prefix}*']}]
            )

            for sg in response['SecurityGroups']:
                sg_id = sg['GroupId']
                print(f"🗑️ Deleting security group {sg_id}...")

                # Delete all ingress rules first
                if sg.get('IpPermissions'):
                    self.ec2.revoke_security_group_ingress(
                        GroupId=sg_id,
                        IpPermissions=sg['IpPermissions']
                    )

                # Delete all egress rules
                if sg.get('IpPermissionsEgress'):
                    self.ec2.revoke_security_group_egress(
                        GroupId=sg_id,
                        IpPermissions=sg['IpPermissionsEgress']
                    )

                # Delete the security group
                try:
                    self.ec2.delete_security_group(GroupId=sg_id)
                    print(f"✅ Deleted security group: {sg_id}")
                except ClientError as e:
                    if 'DependencyViolation' in str(e):
                        print(f"⚠️ Security group {sg_id} is still in use, will retry later...")
                        return sg_id
                    raise e

        except ClientError as e:
            print(f"❌ Error deleting security groups: {e}")

    def _wait_for_dynamodb_table_deletion(self, table_name: str) -> None:
        """Wait for DynamoDB table to be deleted"""
        waiter = self.dynamodb.get_waiter('table_not_exists')
        waiter.wait(
            TableName=table_name,
            WaiterConfig={'Delay': 5, 'MaxAttempts': 20}
        )


def main():
    parser = argparse.ArgumentParser(description='Clean up AWS infrastructure for YouFlix')
    parser.add_argument('--profile', default='default', help='AWS profile to use')
    parser.add_argument('--region', default='us-east-1', help='AWS region to use')
    parser.add_argument('--config', default='aws_config.json', help='Path to configuration file')
    parser.add_argument('--app-name', required=True, help='Application name prefix for resources')
    args = parser.parse_args()

    # Initialize AWS resource cleaner
    aws = AWSResourceCleaner(args.profile, args.region)

    try:
        # Load configuration
        try:
            with open(args.config, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            print(f"⚠️ Configuration file {args.config} not found, will attempt to delete resources based on app name")
            config = {}

        print("🧹 Starting cleanup process...")

        # Delete Elastic Beanstalk application first (this can take a while)
        print("\n>>> Cleaning up Elastic Beanstalk resources...")
        aws.delete_elastic_beanstalk_app(args.app_name)

        # Delete S3 bucket
        print("\n>>> Cleaning up S3 resources...")
        bucket_name = config.get('s3', {}).get('bucket_name', f"{args.app_name}-movies")
        aws.delete_s3_bucket(bucket_name)

        # Delete DynamoDB tables
        print("\n>>> Cleaning up DynamoDB resources...")
        table_names = [
            f"{args.app_name}-movies",
            f"{args.app_name}-comments"
        ]
        if config.get('dynamodb'):
            table_names = list(config['dynamodb'].values())
        aws.delete_dynamodb_tables(table_names)

        # Delete RDS instance
        print("\n>>> Cleaning up RDS resources...")
        db_identifier = config.get('rds', {}).get('db_identifier', f"{args.app_name}-db")
        aws.delete_rds_instance(db_identifier)

        # Delete parameters from Parameter Store
        print("\n>>> Cleaning up Parameter Store resources...")
        aws.delete_parameters(args.app_name)

        # Delete security groups
        print("\n>>> Cleaning up security groups...")
        aws.delete_security_groups(f"{args.app_name}")

        print("\n✅ Cleanup completed successfully!")

        # Clean up the configuration file
        try:
            import os
            os.remove(args.config)
            print(f"✅ Deleted configuration file: {args.config}")
        except OSError:
            pass

    except Exception as e:
        print(f"\n❌ Error during cleanup: {str(e)}")
        raise


if __name__ == "__main__":
    main()
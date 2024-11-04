import boto3
import os
import time
import shutil
import argparse
from typing import Dict
from pathlib import Path
from botocore.exceptions import ClientError
from datetime import datetime


class EBDeployer:
    def __init__(self, profile: str = 'default', region: str = 'us-east-1'):
        """Initialize AWS clients"""
        session = boto3.Session(profile_name=profile, region_name=region)
        self.eb = session.client('elasticbeanstalk')
        self.s3 = session.client('s3')
        self.region = region
        self.deployment_bucket = f"elasticbeanstalk-{region}-{boto3.client('sts').get_caller_identity()['Account']}"

    def create_deployment_package(self, source_dir: str) -> str:
        """Create a ZIP deployment package"""
        print("📦 Creating deployment package...")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"deployment_{timestamp}.zip"

        # Create a temporary directory for the deployment package
        temp_dir = Path("temp_deploy")
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir()

        try:
            # Copy required files to temp directory
            ignore_patterns = [
                '__pycache__',
                '*.pyc',
                '.git',
                '.github',
                '.idea',
                '.venv',
                'venv',
                'tests',
                '.pytest_cache',
                'temp_deploy',
                '*.zip',
                'codebase.md'
            ]

            def ignore_func(directory: str, contents: list) -> list:
                return [item for item in contents if
                        any(pattern in f"{directory}/{item}" for pattern in ignore_patterns)]

            shutil.copytree(source_dir, temp_dir / "app", ignore=ignore_func, dirs_exist_ok=True)

            # Create the ZIP file
            shutil.make_archive(zip_filename[:-4], 'zip', temp_dir / "app")

            print(f"✅ Created deployment package: {zip_filename}")
            return zip_filename

        finally:
            # Cleanup temporary directory
            shutil.rmtree(temp_dir)

    def upload_to_s3(self, filename: str) -> Dict[str, str]:
        """Upload deployment package to S3"""
        print(f"📤 Uploading {filename} to S3...")
        try:
            self.s3.upload_file(
                filename,
                self.deployment_bucket,
                f"deploy/{filename}"
            )
            print(f"✅ Uploaded deployment package to S3")
            return {
                "s3_bucket": self.deployment_bucket,
                "s3_key": f"deploy/{filename}"
            }
        except ClientError as e:
            print(f"❌ Failed to upload to S3: {e}")
            raise

    def deploy_to_eb(
            self,
            app_name: str,
            env_name: str,
            s3_bucket: str,
            s3_key: str,
            wait: bool = True
    ) -> None:
        """Deploy application to Elastic Beanstalk"""
        print(f"🚀 Deploying to Elastic Beanstalk...")

        try:
            # Create application version
            version_label = s3_key.split('/')[-1].replace('.zip', '')
            self.eb.create_application_version(
                ApplicationName=app_name,
                VersionLabel=version_label,
                SourceBundle={
                    'S3Bucket': s3_bucket,
                    'S3Key': s3_key
                },
                AutoCreateApplication=True
            )

            # Check if environment exists
            environments = self.eb.describe_environments(
                ApplicationName=app_name,
                EnvironmentNames=[env_name],
                IncludeDeleted=False
            )['Environments']

            active_environments = [
                env for env in environments
                if env['Status'] not in ['Terminated', 'Terminating']
            ]

            if not active_environments:
                print(f"Creating new environment: {env_name}")
                # Get latest Python platform
                platforms = self.eb.list_available_solution_stacks()['SolutionStacks']
                python_platform = next(p for p in platforms if 'Python' in p and '3.9' in p)

                # Create new environment with updated configuration
                self.eb.create_environment(
                    ApplicationName=app_name,
                    EnvironmentName=env_name,
                    SolutionStackName=python_platform,
                    VersionLabel=version_label,
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
                        },
                        {
                            'Namespace': 'aws:elasticbeanstalk:environment',
                            'OptionName': 'EnvironmentType',
                            'Value': 'SingleInstance'
                        },
                        {
                            'Namespace': 'aws:autoscaling:launchconfiguration',
                            'OptionName': 'IamInstanceProfile',
                            'Value': 'aws-elasticbeanstalk-ec2-role'
                        }
                    ]
                )
            else:
                # Update existing environment
                print(f"Updating existing environment: {env_name}")
                self.eb.update_environment(
                    ApplicationName=app_name,
                    EnvironmentName=env_name,
                    VersionLabel=version_label
                )

            if wait:
                self._wait_for_deployment(app_name, env_name)

            print(f"✅ Deployment completed successfully")

        except Exception as e:
            print(f"❌ Deployment failed: {e}")
            raise

    def _wait_for_deployment(self, app_name: str, env_name: str, timeout: int = 600) -> None:
        """Wait for deployment to complete"""
        print("⏳ Waiting for deployment to complete...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = self.eb.describe_environments(
                    ApplicationName=app_name,
                    EnvironmentNames=[env_name]
                )

                if not response['Environments']:
                    raise Exception(f"Environment {env_name} not found")

                env = response['Environments'][0]
                status = env['Status']
                health = env['Health']

                if status == 'Ready':
                    if health == 'Green':
                        print("✅ Environment is up and healthy")
                        return
                    elif health == 'Red':
                        raise Exception("Environment is in Red health status")

                print(f"⏳ Current status: {status}, Health: {health}")
                time.sleep(10)

            except ClientError as e:
                print(f"❌ Error checking deployment status: {e}")
                raise

        raise Exception("Deployment timed out")


def main():
    parser = argparse.ArgumentParser(description='Deploy FastAPI application to AWS Elastic Beanstalk')
    parser.add_argument('--profile', default='default', help='AWS profile to use')
    parser.add_argument('--region', default='us-east-1', help='AWS region to deploy to')
    parser.add_argument('--app-name', required=True, help='Elastic Beanstalk application name')
    parser.add_argument('--env-name', required=True, help='Elastic Beanstalk environment name')
    parser.add_argument('--source-dir', default='.', help='Source directory containing the application')
    parser.add_argument('--no-wait', action='store_true', help='Don\'t wait for deployment to complete')
    args = parser.parse_args()

    try:
        # Initialize deployer
        deployer = EBDeployer(args.profile, args.region)

        # Create deployment package
        package_file = deployer.create_deployment_package(args.source_dir)

        try:
            # Upload to S3
            s3_info = deployer.upload_to_s3(package_file)

            # Deploy to Elastic Beanstalk
            deployer.deploy_to_eb(
                args.app_name,
                args.env_name,
                s3_info['s3_bucket'],
                s3_info['s3_key'],
                not args.no_wait
            )

        finally:
            # Cleanup deployment package
            if os.path.exists(package_file):
                os.remove(package_file)
                print(f"🧹 Cleaned up deployment package")

    except Exception as e:
        print(f"\n❌ Deployment failed: {str(e)}")
        raise

    print("\n✅ Deployment process completed successfully!")


if __name__ == "__main__":
    main()
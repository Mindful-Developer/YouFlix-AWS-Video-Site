import boto3
import json
import time
from botocore.exceptions import ClientError


def create_eb_roles():
    """Create required IAM roles for Elastic Beanstalk"""
    iam = boto3.client('iam')

    # Create EC2 role
    ec2_role_name = 'aws-elasticbeanstalk-ec2-role'
    ec2_role_document = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": "ec2.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }]
    }

    # Create service role
    service_role_name = 'aws-elasticbeanstalk-service-role'
    service_role_document = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "Service": "elasticbeanstalk.amazonaws.com"
            },
            "Action": "sts:AssumeRole"
        }]
    }

    try:
        # Create EC2 role
        print("Creating EC2 role...")
        iam.create_role(
            RoleName=ec2_role_name,
            AssumeRolePolicyDocument=json.dumps(ec2_role_document)
        )

        # Attach managed policies to EC2 role
        ec2_policies = [
            'arn:aws:iam::aws:policy/AWSElasticBeanstalkWebTier',
            'arn:aws:iam::aws:policy/AWSElasticBeanstalkMulticontainerDocker',
            'arn:aws:iam::aws:policy/AWSElasticBeanstalkWorkerTier'
        ]

        for policy in ec2_policies:
            iam.attach_role_policy(
                RoleName=ec2_role_name,
                PolicyArn=policy
            )

        # Create EC2 instance profile
        print("Creating EC2 instance profile...")
        iam.create_instance_profile(
            InstanceProfileName=ec2_role_name
        )

        # Add role to instance profile
        iam.add_role_to_instance_profile(
            InstanceProfileName=ec2_role_name,
            RoleName=ec2_role_name
        )

        # Create service role
        print("Creating service role...")
        iam.create_role(
            RoleName=service_role_name,
            AssumeRolePolicyDocument=json.dumps(service_role_document)
        )

        # Attach managed policy to service role
        iam.attach_role_policy(
            RoleName=service_role_name,
            PolicyArn='arn:aws:iam::aws:policy/service-role/AWSElasticBeanstalkService'
        )

        # Wait for roles to propagate
        print("Waiting for roles to propagate...")
        time.sleep(10)

        print("✅ Successfully created IAM roles for Elastic Beanstalk")

    except ClientError as e:
        if e.response['Error']['Code'] == 'EntityAlreadyExists':
            print("⚠️ IAM roles already exist")
        else:
            raise e


if __name__ == "__main__":
    create_eb_roles()
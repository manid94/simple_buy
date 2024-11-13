import time
import json
import boto3

# Open the JSON file and load the data
with open('my.json', 'r') as file:
    data = json.load(file)

# Print the data to verify it's loaded
print(data)


kk = data['k'].split('--')
pp = data['p'].split('--')



ec2 = boto3.client(
    'ec2',
    aws_access_key_id=kk[1],
    aws_secret_access_key=pp[1],
    region_name='ap-south-1'  # Set your region
)

def start_instance(instance_id = 'i-0159b8df7a098d490', region='us-west-2'):
    # ec2 = boto3.client('ec2', region_name=region)
    response = ec2.start_instances(InstanceIds=[instance_id])
    print(f'Starting instance {instance_id}')
    return response

def stop_instance(instance_id='i-0159b8df7a098d490', region='us-west-2'):
    #ec2 = boto3.client('ec2', region_name=region)
    response = ec2.stop_instances(InstanceIds=[instance_id])
    print(f'Stopping instance {instance_id}')
    return response

# Replace 'your-instance-id' with your actual instance ID
instance_id = 'i-0159b8df7a098d490'
region = 'ap-south-1'  # Specify your region

# To start the instance
start_instance(instance_id, region)

time.sleep(100)
# To stop the instance
stop_instance(instance_id, region)

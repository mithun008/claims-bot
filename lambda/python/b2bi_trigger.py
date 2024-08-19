import boto3
import os
import json
# Create a B2BI client
b2bi_client = boto3.client("b2bi")


def main(event, context):
    print(json.dumps(event))

    
    # Parse the S3 event from EventBridge
    
    bucket_name = event["detail"]["bucket"]["name"]
    file_key = event["detail"]["object"]["key"]
    
    print("Input file detected")

    # Define the input file location (S3 bucket and key)
    input_file = {"bucketName": bucket_name, "key": file_key}
    print(json.dumps(input_file))

    # Define the output location (S3 bucket and prefix)
    # get bucket name from environment variable
    output_bucket_name = os.environ["OUTPUT_BUCKET_NAME"]
    output_location = {
        "bucketName":output_bucket_name,
        "key": 'out-claim.json'
    }

    print(json.dumps(output_location))

    # Define the transformer ID
    claim_transformer_id = os.environ["CLAIM_TRANSFORMER_ID"]
    remit_transformer_id = os.environ["REMIT_TRANSFORMER_ID"]

    print(file_key)
    transformer_id = ''
    if file_key.startswith("input/837"):
        fileType = "837"
        print("837 file detected")
        transformer_id = claim_transformer_id
        # Start the transformer job

    if file_key.startswith("input/835"):
        fileType = "835"
        print("835 file detected")
        transformer_id = remit_transformer_id

    response = b2bi_client.start_transformer_job(
        inputFile={
            'bucketName': bucket_name,
            'key': file_key
        },
        outputLocation={
            'bucketName': output_bucket_name,
            'key': 'output/'
        },
        transformerId=transformer_id,
    )
    # Get the transformer job ID from the response
    transformer_job_id = response["transformerJobId"]

    # Print the transformer job ID
    print(f"Transformer job started: {transformer_job_id}")

    return {"statusCode": 200, "body": f"Transformer job started: {transformer_job_id}"}

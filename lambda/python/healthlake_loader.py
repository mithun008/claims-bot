import json
import boto3
from requests_auth_aws_sigv4 import AWSSigV4
import os
import requests


hl_datastore_id = os.environ.get('HL_DATASTORE_ID')
fhir_bucket_name = os.environ.get('FHIR_TEMPLATE_BUCKET')

s3 = boto3.client('s3')

def convert_claim_edi_to_fhir(claim_edi):
    print("Inside convert_claim_edi_to_fhir")
    
    print(fhir_bucket_name)
    # read object from S3 bucket
    try:
        response = s3.get_object(Bucket=fhir_bucket_name, Key='claim-fhir.json')
        object_data = response['Body'].read().decode('utf-8')

        return object_data
    except s3.exceptions.NoSuchKey:
        print(f"Object '{object_key}' not found in bucket '{bucket_name}'")
        return None

def convert_remit_edi_to_fhir(remit_edi):
    print("Inside convert_remit_edi_to_fhir")

    print(fhir_bucket_name)
    # read object from S3 bucket
    try:
        # convert remit edi to fhir
        
        response = s3.get_object(Bucket=fhir_bucket_name, Key='eob-fhir.json')
        object_data = response['Body'].read().decode('utf-8')

        return object_data
    except s3.exceptions.NoSuchKey:
        print(f"Object '{object_key}' not found in bucket '{bucket_name}'")
        return None

def transform_to_FHIR(event,context):
    print(json.dumps(event))
    headers = { 'content-type': 'application/json+fhir' }

    bucket_name = event["detail"]["bucket"]["name"]
    file_key = event["detail"]["object"]["key"]

    print(bucket_name, file_key)

    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    ediJSON = response['Body'].read().decode('utf-8')
 

    resourceType = ''

    fhirBody = ''
 
    # check if resourceType is equal to Claim
    if file_key.startswith("output/837"):
        print('Resource type is Claim')
        resourceType = 'Claim'
        print(type(ediJSON))
        # get object from S3 bucket
        fhirBody = convert_claim_edi_to_fhir(ediJSON)
        print(fhirBody)
    else: #resourceType is ExplanationOfBenefit
        resourceType = 'ExplanationOfBenefit'
        fhirBody = convert_remit_edi_to_fhir(ediJSON)
        print(fhirBody)
    print(os.environ.get('AWS_REGION'))

    print(hl_datastore_id)


    aws_auth = AWSSigV4(service = 'healthlake', region = os.environ.get('AWS_REGION'),
        aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key = os.environ.get(
            'AWS_SECRET_ACCESS_KEY'),
        aws_session_token = os.environ.get('AWS_SESSION_TOKEN')
    )

    
    hl_response = requests.request('POST', 
        'https://healthlake.us-west-2.amazonaws.com/datastore/' + hl_datastore_id + '/r4/'+resourceType,
        auth = aws_auth, data = fhirBody, headers = headers)
    response_body = hl_response.json()
    print('Healthlake response is {}'.format(response_body))

    return response_body;


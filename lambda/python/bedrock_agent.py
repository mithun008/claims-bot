import json
import boto3
from requests_auth_aws_sigv4 import AWSSigV4
import os
import requests

hl_datastore_id = os.environ.get("HEALTHLAKE_ID")


def get_eob_for_claim(claim_id):
    headers = {"Accept": "application/json+fhir"}
    params = {"claim": claim_id}
    # Get the EOB for the claim
    aws_auth = AWSSigV4(
        service="healthlake",
        region=os.environ.get("AWS_REGION"),
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )

    hl_response = requests.request(
        "GET",
        "https://healthlake.us-west-2.amazonaws.com/datastore/"
        + hl_datastore_id
        + "/r4/"
        + 'ExplanationOfBenefit',
        auth=aws_auth,
        headers=headers,
        params=params,
    )
    response_body = hl_response.json()
    eob_response = json.dumps(response_body['entry'][0]['resource'])
    print("Healthlake response is {}".format(eob_response))
    return eob_response


def main(event, context):
    print("Event: {}".format(event))
    agent = event['agent']
    actionGroup = event['actionGroup']
    function = event['function']
    parameters = event.get('parameters', [])
    claimId = parameters[0]['value']
    
    print('Claim Id is {}'.format(claimId))

    # Execute your business logic here. For more information, refer to: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-lambda.html
    # eob_fhir = get_eob_for_claim(parameters['claimId'])
    eob_fhir = get_eob_for_claim("Claim/"+claimId)
    
    responseBody =  {
        "TEXT": {
            "body": eob_fhir
        }
    }

    action_response = {
        'actionGroup': actionGroup,
        'function': function,
        'functionResponse': {
            'responseBody': responseBody
        }

    }

    function_response = {'response': action_response, 'messageVersion': event['messageVersion']}
    print("Response: {}".format(function_response))

    return function_response


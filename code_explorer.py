import boto3
from datetime import datetime, timedelta
import json

def get_aws_billing_data(start_date, end_date, filters=None):
    client = boto3.client('ce')

    query = {
        'TimePeriod': {'Start': start_date, 'End': end_date},
        'Granularity': 'MONTHLY',
        'Metrics': ['UnblendedCost'],
        'GroupBy': [{'Type': 'DIMENSION', 'Key': 'SERVICE'}]
    }

    if filters:
        query['Filter'] = filters

    try:
        response = client.get_cost_and_usage(**query)
        return response
    except Exception as e:
        raise RuntimeError(f"Cost Explorer Error: {str(e)}")


def format_table(data):
    if not data:
        return "No billing data available"
    
    service_width = max(len(item['Service']) for item in data)
    cost_width = max(len(f"{item['Cost (USD)']:.2f}") for item in data)

    table = [
        f"| {'Service'.ljust(service_width)} | {'Cost (USD)'.rjust(cost_width)} |",
        f"|{'-' * (service_width + 2)}|{'-' * (cost_width + 2)}|"
    ]

    for item in sorted(data, key=lambda x: x['Cost (USD)'], reverse=True):
        service = item['Service'].ljust(service_width)
        cost = f"{item['Cost (USD)']:.2f}".rjust(cost_width)
        table.append(f"| {service} | {cost} |")

    return "\n".join(table)


def build_filters(params):
    filters = []

    # Service filter
    if 'services' in params:
        filters.append({
            'Dimensions': {
                'Key': 'SERVICE',
                'Values': params['services'].split(',')
            }
        })

    # Region filter
    if 'regions' in params:
        filters.append({
            'Dimensions': {
                'Key': 'REGION',
                'Values': params['regions'].split(',')
            }
        })

    # Tag filters (dynamic)
    for param_key in params:
        if param_key.startswith('tag_'):
            tag_name = param_key[4:]  # Remove 'tag_' prefix
            tag_values = params[param_key].split(',')
            filters.append({
                'Tags': {
                    'Key': tag_name,
                    'Values': tag_values
                }
            })

    # Return combined filter
    if not filters:
        return None
    elif len(filters) == 1:
        return filters[0]
    else:
        return {'And': filters}


def lambda_handler(event, context):
    try:
        params = event.get('queryStringParameters', {}) or {}

        # Default to current month start and yesterday's date
        try:
            start_date = params.get('start_date',
                                    datetime.now().replace(day=1).strftime('%Y-%m-%d'))
            end_date = params.get('end_date',
                                  (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'))

            # Validate date format
            datetime.strptime(start_date, '%Y-%m-%d')
            datetime.strptime(end_date, '%Y-%m-%d')

            if datetime.strptime(start_date, '%Y-%m-%d') > datetime.strptime(end_date, '%Y-%m-%d'):
                raise ValueError("start_date must be before end_date")

        except ValueError as e:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f"Invalid date: {str(e)}"})
            }

        # Build any filters
        filters = build_filters(params)

        # Get billing data
        response = get_aws_billing_data(start_date, end_date, filters)

        formatted_data = []
        if response:
            for result in response['ResultsByTime']:
                for group in result['Groups']:
                    service = group['Keys'][0]
                    cost = round(float(group['Metrics']['UnblendedCost']['Amount']), 2)
                    formatted_data.append({'Service': service, 'Cost (USD)': cost})

        # Determine output format: JSON or table
        output_format = params.get('format', 'json').lower()  # default is JSON

        if output_format == 'table':
            body = format_table(formatted_data) if formatted_data else "No data found"
            headers = {'Content-Type': 'text/plain'}
        else:
            body = json.dumps({'data': formatted_data}) if formatted_data else json.dumps({'message': 'No data found'})
            headers = {'Content-Type': 'application/json'}

        return {
            'statusCode': 200,
            'headers': headers,
            'body': body
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


# Local testing
if __name__ == '__main__':
    test_event = {
        'queryStringParameters': {
            'start_date': '2025-03-03',
            'end_date': '2025-03-31',
            'regions': 'us-east-1',
            'format': 'json'
        }
    }
    result = lambda_handler(test_event, None)
    print(result['body'])

import argparse
import csv
from jinja2 import Environment, FileSystemLoader
import os
import sys
from datetime import datetime, timezone, timedelta

def process_csv(csv_file):
    traffic_data = []
    total_gb = None

    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Extract required fields
            entry = {
                'date': row['UTC8_Date'],
                'upload': float(row['Accumulated_Upload_GB']),
                'download': float(row['Accumulated_Download_GB']),
                'totalUsed': float(row['Total_Used_GB']),
                'usedPercent': float(row['Used_Percent'])
            }
            traffic_data.append(entry)

            # Get total traffic value (same for all rows)
            if total_gb is None:
                total_gb = float(row['Total_GB'])

    return traffic_data, total_gb

def generate_html(output_file, traffic_data, total_gb, discard_day1):
    # Set up Jinja environment
    env = Environment(loader=FileSystemLoader('.'))
    template = env.get_template('template.html')

    # Get current UTC+8 time
    utc8 = timezone(timedelta(hours=8))
    current_time = datetime.now(utc8).strftime("%Y-%m-%d %H:%M:%S")

    # Render template
    html_output = template.render(
        traffic_data=traffic_data,
        total_gb=total_gb,
        current_time=current_time,
        discard_day1=discard_day1
    )

    # Write output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_output)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Generate traffic usage dashboard')
    parser.add_argument('csv_file', help='Input CSV file path')
    parser.add_argument('output_file', help='Output HTML file path')
    parser.add_argument('--discard-day1', action='store_true',
                        help='Discard first day in daily upload/download chart (original behavior). '
                             'By default, first day is kept with value 0.')
    args = parser.parse_args()

    # Process data
    traffic_data, total_gb = process_csv(args.csv_file)

    # Generate HTML
    generate_html(args.output_file, traffic_data, total_gb, args.discard_day1)

    print(f"Successfully generated dashboard page: {args.output_file}")

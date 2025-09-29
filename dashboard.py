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

def generate_html(output_file, traffic_data, total_gb):
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
        current_time=current_time
    )

    # Write output file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_output)

if __name__ == "__main__":
    # Check command line arguments
    if len(sys.argv) != 3:
        print("Usage: python dashboard.py <csv_file> <output_file>")
        sys.exit(1)

    # Get file paths from command line arguments
    csv_file = sys.argv[1]
    output_file = sys.argv[2]

    # Process data
    traffic_data, total_gb = process_csv(csv_file)

    # Generate HTML
    generate_html(output_file, traffic_data, total_gb)

    print(f"Successfully generated dashboard page: {output_file}")

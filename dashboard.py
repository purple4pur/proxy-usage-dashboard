import argparse
import csv
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader


def process_csv(csv_file):
    traffic_data = []
    total_gb     = None
    fields       = {
        'upload': 'Accumulated_Upload_GB',
        'download': 'Accumulated_Download_GB',
        'totalUsed': 'Total_Used_GB',
        'usedPercent': 'Used_Percent',
    }

    with open(csv_file, 'r', encoding='utf-8-sig', newline='') as stream:
        reader   = csv.DictReader(stream)
        required = ['UTC8_Date', 'Total_GB', *fields.values()]
        headers  = reader.fieldnames or []
        if any(headers.count(field) != 1 for field in required):
            raise ValueError('CSV must contain each required column exactly once: ' + ', '.join(required))
        for row in reader:
            day = row['UTC8_Date']
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError(f'CSV line {reader.line_num}: UTC8_Date must use YYYY-MM-DD')
            entry = {'date': day}
            for key, field in fields.items():
                value = float(row[field])
                if not math.isfinite(value) or value < 0:
                    raise ValueError(f'CSV line {reader.line_num}: {field} must be finite and nonnegative')
                entry[key] = value
            quota = float(row['Total_GB'])
            if not math.isfinite(quota) or quota < 0:
                raise ValueError(f'CSV line {reader.line_num}: Total_GB must be finite and nonnegative')
            traffic_data.append(entry)
            if total_gb is None:
                total_gb = quota

    return traffic_data, total_gb


def generate_html(output_file,
                  traffic_data,
                  total_gb,
                  discard_day1):
    env      = Environment(loader=FileSystemLoader(Path(__file__).resolve().parent), autoescape=True)
    template = env.get_template('template.html')
    utc8     = timezone(timedelta(hours=8))

    current_time = datetime.now(utc8).strftime('%Y-%m-%d %H:%M:%S')
    html_output  = template.render(traffic_data=traffic_data, total_gb=total_gb, current_time=current_time, discard_day1=discard_day1)
    with open(output_file, 'w', encoding='utf-8') as stream:
        stream.write(html_output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate traffic usage dashboard')
    parser.add_argument('csv_file', help='Input CSV file path')
    parser.add_argument('output_file', help='Output HTML file path')
    parser.add_argument('--discard-day1', action='store_true', help='Discard the first daily upload/download sample. By default, use its accumulated values.')
    args = parser.parse_args()

    traffic_data, total_gb = process_csv(args.csv_file)
    generate_html(args.output_file, traffic_data, total_gb, args.discard_day1)
    print(f'Successfully generated dashboard page: {args.output_file}')

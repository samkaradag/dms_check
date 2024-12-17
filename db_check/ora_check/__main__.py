import yaml
import oracledb
import os
import argparse
import pathlib
import datetime
from google.cloud import secretmanager

def get_script_path():
    """Returns the absolute path of the currently executing script."""
    return os.path.dirname(os.path.abspath(__file__))

def get_secret(secret_name):
    """Fetches the secret value from Google Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is not set.")
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(name=secret_path)
    return response.payload.data.decode("UTF-8")

def resolve_password(password_arg):
    """Resolves the password from the argument or Google Secret Manager."""
    if password_arg and password_arg.startswith("gcp-secret:"):
        secret_name = password_arg.split("gcp-secret:")[1]
        return get_secret(secret_name)
    return password_arg

def load_config(config_file):
    # Load the YAML configuration file
    script_dir = pathlib.Path(__file__).parent.resolve()
    config_file_path = script_dir / config_file
    with open(config_file_path, 'r') as f:
        return yaml.safe_load(f)

def run_checks(cur, checks, owner_exclude_list):
    results = []
    for check in checks:
        print(f"Running check: {check['name']}")
        formatted_query = check['query'].replace("{owner_exclude_list}", ", ".join([f"'{owner}'" for owner in owner_exclude_list]))
        
        cur.execute(formatted_query)
        rows = cur.fetchall()

        # Format and store the results
        if rows:
            results.append({
                'name': check['name'],
                'description': check.get('description', ''),
                'warning': check.get('warning_message', ''),
                'rows': rows
            })
    return results

def format_results(results):
    # Create a readable output format for validation results
    for result in results:
        print(f"Check: {result['name']}")
        print(result['description'])
        print(result['warning'])
        print("Result:")
        for row in result['rows']:
            print(f"  - {row}")
        print("\n")

def generate_html_report(results):
    """Generates an HTML report from the results."""
    # html = ["<html>", "<head>", "<title>Database Validation Report</title>", "</head>", "<body>"]
    html_header = """
    <!DOCTYPE html>
    <html>
    <head>
    <title>DMS Compatibility Report</title>"""

    # Include CSS files
    css_folder = os.path.join(get_script_path(), 'css')
    for filename in os.listdir(css_folder):
        if filename.endswith('.css'):
            with open(os.path.join(css_folder, filename), 'r') as css_file:
                html_header += "<style>\n" + css_file.read() + "\n</style>\n"

    html_header += """<style>
    body {
        font-family: 'Arial', sans-serif;
        background-color: #f4f4f4;
        color: #333;
        line-height: 1.6;
        margin: 0;
        padding: 20px;
      }
      
      h2 {
        color: #4285f4;
        margin-bottom: 1em;
      }
      
      h3 {
        color: #4285f4;
        margin-top: 2em;
        margin-bottom: 1em;
      }
      
      /* Menu Styling */
        ul {
            list-style-type: none;
            padding: 0;
            margin: 0;
            overflow: hidden; /* Hide overflowing menu items */
        }

        li {
            display: inline-block; /* Horizontal menu items */
            margin: 0;  /* Remove default margin */
        }

        li a {
            color: white; /* White text */
            display: block; /* Make the entire list item clickable */
            padding: 14px 16px; /* Padding around the link text */
            text-decoration: none; /* Remove underlines */
            transition: background-color 0.3s ease; /* Smooth background transition */
        }

        li a:hover {
            background-color: #307bf5; /* Darker background on hover */
        }
      
      table {
        border-collapse: collapse;
        width: 100%;
        margin-bottom: 2em;
        background-color: #fff;
        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
      }
      
      th, td {
        border: 1px solid #ddd;
        padding: 8px;
        text-align: left;
      }
      
      th {
        background-color: #f0f0f0;
        font-weight: bold;
      }
      
      tr:nth-child(even) {
        background-color: #f9f9f9;
      }
      
      tr:hover {
        background-color: #e0e0e0;
      }
      
      .missing {
        color: #c0392b;
        font-weight: bold;
      }
      
      .present {
        color: #2ecc71;
        font-weight: bold;
      }
      .back-to-top {
        position: fixed;
        bottom: 20px;
        right: 20px;
        display: none; /* Hidden by default */
        background-color: #007bff; /* Blue background */
        color: white;
        padding: 10px;
        border-radius: 50%;
        cursor: pointer;
    }
    .back-to-top:hover {
        background-color: #4285f4;
    }
    .back-to-top i { /* Style the arrow icon */
        font-size: 1.2em;
        line-height: 1;
    }
    </style>
    </head>
    <body>
    <h1>DMS Compatibility Report</h1>
    <ul>
    """

    html = [html_header]
    html.append(f"<p>Generated on: {datetime.datetime.now()}</p>")

    for result in results:
        html.append(f"<h2>{result['name']}</h2>")
        html.append(f"<p>{result['description']}</p>")
        if result['warning']:
            html.append(f"<p style='color:orange;'><strong>Warning:</strong> {result['warning']}</p>")
        html.append("<table border='1' style='border-collapse: collapse; width: 100%;'>")
        html.append("<tr><th>Findings</th></tr>")
        for row in result['rows']:
            html.append(f"<tr><td>{', '.join(map(str, row))}</td></tr>")
        html.append("</table>")
    
    html.append("</body>")
    html.append("</html>")
    return "\n".join(html)

def validate_database(db_user, db_password, db_host, db_port, db_service, tns, tns_path, config_file, view_type='all', protocol='tcp', output_format='text'):
    """
    Validates Oracle database with a set of checks from a configuration file.
    """
    # Load checks from YAML configuration
    config = load_config(config_file)

    # Construct the connection string
    # dsn = oracledb.makedsn(host=db_host, port=db_port, service_name=db_service)
    # conn = oracledb.connect(user=db_user, password=db_password, dsn=dsn, protocol=protocol)

    # Construct the connection string
    if tns:
        dsn = tns
        # oracledb.init_oracle_client(lib_dir=tns_path.replace("/network/admin", ""))  # Point to the Oracle client libraries
        oracledb.init_oracle_client() 
        conn = oracledb.connect(
            user=db_user,
            password=db_password,
            dsn=dsn,
            config_dir=tns_path,
            ssl_server_dn_match=False  # Disable SSL certificate validation
        )
    else:
        dsn = oracledb.makedsn(host=db_host, port=db_port, service_name=db_service)
         # Connect to the database
        conn = oracledb.connect(
            user=db_user,
            password=db_password,
            dsn=dsn,
            protocol=protocol
        )

    # Create a cursor object
    cur = conn.cursor()

    # Run the checks
    results = run_checks(cur, config['validations'], config['owner_exclude_list'])

    if tns:
        db_host_alpha = ''.join(c for c in tns if c.isalpha())
    else:
        # db_host_alpha = ''.join(c for c in db_host if c.isalpha()) 
        if all(c.isdigit() or c == '.' for c in db_host):
        # Remove the periods and prefix with 'ip_'
            db_host_alpha = 'ip_' + db_host.replace('.', '_')
        else:
            # If it's not an IP, just extract alphabetic characters
            db_host_alpha = ''.join(c for c in db_host if c.isalpha())

    # Generate report filename with database host and timestamp
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_name = f"dms_comp_{db_host_alpha}_{timestamp}.html"

    if output_format == 'text':
        format_results(results)
    elif output_format == 'html':
        html_report = generate_html_report(results)
        with open(report_name, "w") as f:
            f.write(html_report)
        print(f"HTML report generated: {report_name}")

    # Close the cursor and connection
    cur.close()
    conn.close()

def main():
    parser = argparse.ArgumentParser(description='Validate Oracle database schema and objects')
    parser.add_argument('--user', type=str, help='Username for the Oracle database')
    parser.add_argument('--password', type=str, help='Password for the Oracle database')
    parser.add_argument('--host', type=str, help='Hostname of the Oracle database')
    parser.add_argument('--port', default='1521', type=str, help='Port number of the Oracle database')
    parser.add_argument('--service', type=str, help='Service name of the Oracle database')
    parser.add_argument('--tns', type=str, help='TNS name (alias) (alternative to --host, --port, --service)')
    parser.add_argument('--tns_path', type=str, help='Path to tnsnames.ora file (alternative to --host, --port, --service)')
    parser.add_argument('--config', default='./config_oracle.yaml', type=str, help='Path to the YAML configuration file')
    parser.add_argument('--view_type', type=str, help='Type of catalog views either "all or "user"')
    parser.add_argument('--protocol', default='tcp', type=str, help='Protocol either "tcp" or "tcps"')
    parser.add_argument("--format", default="text", choices=["text", "html"], help="Output format (text or html)")

    args = parser.parse_args()

    password = resolve_password(args.password)

    # Determine connection method based on provided arguments.
    if args.tns:
      validate_database(
        args.user, password, None, None, None, args.tns, args.tns_path, args.config, args.view_type, None, args.format
      )
    elif args.host and args.port and args.service:
      validate_database(
        args.user, password, args.host, args.port, args.service, None, None, args.config, args.view_type, args.protocol, args.format
      )
    else:
      print("Error: Please provide either --tns OR --host, --port, and --service.")
      
    

if __name__ == "__main__":
    main()

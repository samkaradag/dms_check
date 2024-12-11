# Oracle Database DMS Checker

This script checks an Oracle database compatibility for DMS, generating a report in either text or HTML format.  It's designed to assist in verifying the readiness of a database for GCP Data Migration Service (DMS) processes.

## Features

* **Configuration-driven:** Uses a YAML configuration file to define the database checks to perform.  This allows for easy customization and maintenance. Simply use --config option to provide a custom yaml.
* **Secure password handling:** Supports password retrieval from Google Cloud Secret Manager, enhancing security.  Alternatively, you can directly provide the password as a command-line argument.
* **Flexible output:** Generates reports in both text and HTML formats. The HTML report includes styling for improved readability.
* **Error handling:** Includes basic error handling for missing environment variables and connection issues.


## Requirements

* **Python 3.9+:** The script is written in Python and requires Python 3.9 or higher.


## Setup
pip install dms_check
1. **Install dependencies:**  Install the Python package: pip install dms_check
2. **(Optional) Configure Google Cloud Secret Manager:** If you choose to store the database password in Google Cloud Secret Manager, set the `GOOGLE_CLOUD_PROJECT` environment variable to your Google Cloud project ID.  Then, refer to the secret in your command-line argument (see Usage section).



## Usage

```bash
ora_check --user <your_oracle_username> --password <your_password> --host <your_host> --port <your_port> --service <your_service_name> [--config <config_file_path>] [--format text|html]
```

* Replace `<your_username>`, `<your_password>`, `<your_host>`, `<your_port>`, and `<your_service_name>` with your Oracle database credentials and connection details.
* You can use `gcp-secret:<secret_name>` for the `--password` argument to retrieve the password from Google Secret Manager.
*  The `--format` argument specifies the output format (`text` or `html`).  Defaults to `text`.


## Example with Google Cloud Secret Manager:

```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
ora_check --user your_username --password gcp-secret:your-secret-name --host your_host --port 1521 --service your_service_name --format html
```

## Example with custom YAML:
**Optional - Configure the YAML file:** If you want to customize checks create/update the `config_oracle.yaml` file (or specify a different path using the `--config` command-line argument) in the same directory as the script.  This file should contain a list of database checks in YAML format.  See the example below.

**Example `config_oracle.yaml`:**

```yaml
owner_exclude_list: ['SYS', 'SYSTEM', 'CTXSYS', 'MDSYS', 'WMSYS', 'XDB', 'ORDDATA', 'AUDSYS', 'OJVMSYS', 'DBSFWUSER','DBSNMP', 'GSMADMIN_INTERNAL', 'DVSYS', 'OUTLN', 'APPQOSSYS', 'ORDSYS', 'LBACSYS']
validations:
  - name: "Unsupported Columns"
    description: "Columns with unsupported data types"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME, 
          COLUMN_NAME, 
          DATA_TYPE 
      FROM DBA_TAB_COLS
      WHERE DATA_TYPE IN (
        'ANYDATA', 'BFILE', 'INTERVAL DAY TO SECOND', 'INTERVAL YEAR TO MONTH', 
        'LONG', 'LONG RAW', 'SDO_GEOMETRY', 'UDT', 'UROWID', 'XMLTYPE'
      )
      AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Warning: The following columns have unsupported data types and will be replaced with NULL values:
  - name: "Lob Data Types"
    description: "Checks for LOB data types"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME, 
          COLUMN_NAME 
      FROM DBA_TAB_COLS 
      WHERE DATA_TYPE IN ('BLOB', 'CLOB', 'NCLOB') AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Warning: The following LOB columns are not replicated unless 'streamLargeObjects' is enabled:
  - name: "Tables without Primary Keys"
    description: "Tables missing primary keys"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME 
      FROM DBA_TABLES 
      WHERE TEMPORARY = 'N' AND OWNER NOT IN ({owner_exclude_list})
      AND (OWNER, TABLE_NAME) NOT IN (
        SELECT OWNER, TABLE_NAME FROM DBA_CONS_COLUMNS WHERE CONSTRAINT_NAME IN (
          SELECT CONSTRAINT_NAME FROM DBA_CONSTRAINTS WHERE CONSTRAINT_TYPE = 'P'
        )
      )
    warning_message: |
      Warning: The following tables have no primary keys, so ROWID will be used for merging and migration operations:
  - name: "Temporary Tables"
    description: "Temporary tables are unsupported"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME 
      FROM DBA_TABLES 
      WHERE TEMPORARY = 'Y' AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Warning: Temporary tables are not supported and will not be replicated:
  - name: "Logminer Limitations"
    description: "Checks for long table or column names that exceed LogMiner limits"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME, 
          COLUMN_NAME 
      FROM DBA_TAB_COLUMNS
      WHERE LENGTH(TABLE_NAME) > 30 OR LENGTH(COLUMN_NAME) > 30 AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Error: The following table or column names exceed LogMiner's 30-character limit and cannot be replicated:
  - name: "LOBs greater than 100mb"
    description: "Checks for lob column if they may exceed DMS limitation of 100mb"
    query: |
      SELECT 
          owner,
          table_name,
          column_name,
          segment_name,
          sum(chunk) / (1024 * 1024) AS total_lob_size_in_mb,
          (sum(chunk) / (1024 * 1024))/COUNT(1) AS avg_lob_size_in_mb
      FROM 
          dba_lobs
      WHERE 
          segment_name IS NOT NULL 
          AND OWNER NOT IN ({owner_exclude_list})
      GROUP BY owner, table_name, column_name, segment_name
      HAVING (sum(chunk) / (1024 * 1024))/COUNT(1) > 100
    warning_message: |
      Warning: The following lob columns may exceed DMS's 100mb limit and cannot be replicated:
  - name: "Unsupported Character Set"
    description: "Checks for unsupported character sets"
    query: |
      SELECT 
          VALUE AS NLS_CHARACTERSET 
      FROM NLS_DATABASE_PARAMETERS
      WHERE parameter='NLS_CHARACTERSET' and VALUE NOT IN ('AL16UTF16', 'AL32UTF8', 'IN8ISCII', 'JA16SJIS', 'US7ASCII', 'UTF8', 'WE8ISO8859P1', 'WE8ISO8859P9', 'WE8ISO8859P15', 'WE8MSWIN1252', 'ZHT16BIG5')
    warning_message: |
      Error: The database character set is not supported.
  - name: "Unsupported Table Names"
    description: "Checks for unsupported characters in table names"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME 
      FROM DBA_TABLES 
      WHERE REGEXP_LIKE(TABLE_NAME, '[^a-zA-Z0-9_]') AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Error: The following table names contain unsupported characters:
  - name: "Unsupported Column Names"
    description: "Checks for unsupported characters in column names"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME, 
          COLUMN_NAME 
      FROM DBA_TAB_COLUMNS 
      WHERE REGEXP_LIKE(COLUMN_NAME, '[^a-zA-Z0-9_]') AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Error: The following column names contain unsupported characters:
  - name: "Too Many Tables"
    description: "Checks if the number of tables exceeds the limit"
    query: |
      SELECT COUNT(*) TABLE_COUNT FROM DBA_TABLES WHERE OWNER NOT IN ({owner_exclude_list})
      HAVING COUNT(*) > 10000
    warning_message: |
      Error: The number of tables exceeds the limit of 10,000.
  - name: "Index-Organized Tables"
    description: "Checks for Index-organized tables"
    query: |
      SELECT 
          OWNER, 
          TABLE_NAME 
      FROM DBA_TABLES 
      WHERE IOT_TYPE IS NOT NULL AND OWNER NOT IN ({owner_exclude_list})
    warning_message: |
      Error: Index-organized tables are not supported:
```


## License
Google 



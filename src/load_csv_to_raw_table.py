
###     load_csv_to_raw_table(fn, table_name, conn)
###     final update 2026-04-09
###  OLAP을 위해서 sql 에 raw data 를 형성하는 것을 자동화하는 코드야 ### 


import pyodbc
import csv
import re


def clean_column_name(col, idx=None):
    col = col.strip().lower()
    col = col.replace(" ", "_")
    col = re.sub(r'[^a-zA-Z0-9_]', '_', col)   # remove special character
    col = re.sub(r'_+', '_', col)              # rearrange underscores
    col = col.strip('_')

    if not col:
        col = f"column_{idx}" if idx is not None else "column_name"

    if col[0].isdigit():
        col = f"col_{col}"

    return col


def load_csv_to_raw_table(fn, table_name, conn):
    """
    Load a CSV file into a SQL Server raw table.
    
    Parameters
    ----------
    fn : str
        Full path to the CSV file
    table_name : str
        SQL Server table name to create/load
    conn : pyodbc.Connection
        Open pyodbc connection
    """
    cur = conn.cursor()

    # 1. Read header
    with open(fn, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        header = next(reader)

    print("CSV header count:", len(header))
    print("CSV header:", header)

    # 2. Clean header + handle duplicates
    clean_header = []
    seen = {}

    for i, col in enumerate(header, start=1):
        cleaned = clean_column_name(col, idx=i)

        if cleaned in seen:
            seen[cleaned] += 1
            cleaned = f"{cleaned}_{seen[cleaned]}"
        else:
            seen[cleaned] = 1

        clean_header.append(cleaned)

    print("Clean header:", clean_header)

    # 3. Drop existing table
    drop_sql = f"""
    IF OBJECT_ID('{table_name}', 'U') IS NOT NULL
        DROP TABLE [{table_name}];
    """
    cur.execute(drop_sql)
    conn.commit()

    # 4. Create raw table
    column_defs = [f"[{col}] VARCHAR(MAX) NULL" for col in clean_header]

    create_sql = f"""
    CREATE TABLE [{table_name}] (
        [id_column] INT NOT NULL IDENTITY(1,1) PRIMARY KEY,
        {', '.join(column_defs)}
    );
    """

    print("=== CREATE SQL ===")
    print(create_sql)

    cur.execute(create_sql)
    conn.commit()

    # 5. Prepare insert SQL
    column_names_sql = ", ".join([f"[{col}]" for col in clean_header])
    placeholders = ", ".join(["?"] * len(clean_header))

    insert_sql = f"""
    INSERT INTO [{table_name}] (
        {column_names_sql}
    ) VALUES (
        {placeholders}
    );
    """

    print("=== INSERT SQL ===")
    print(insert_sql)

    # 6. Read rows
    data_rows = []

    with open(fn, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        next(reader)  # skip header

        for row_num, row in enumerate(reader, start=2):
            if len(row) < len(clean_header):
                row = row + [""] * (len(clean_header) - len(row))
            elif len(row) > len(clean_header):
                row = row[:len(clean_header)]

            data_rows.append(tuple(row))

    print("Rows to insert:", len(data_rows))

    # 7. Insert rows
    cur.fast_executemany = True
    cur.executemany(insert_sql, data_rows)
    conn.commit()

    print("INSERT complete")

    # 8. Check row count
    cur.execute(f"SELECT COUNT(*) FROM [{table_name}];")
    row_count = cur.fetchone()[0]
    print("Rows in table:", row_count)

    cur.close()

    return clean_header, row_count
    
    """
    load_csv_to_raw_table(fn, table_name, conn)
    연결방법  1. server 연결 2. csv파일 3. table name
    __________________________________________________

    conn = pyodbc.connect(
    "DRIVER={SQL Server};"
    "SERVER=127.0.0.1,1433;"
    "DATABASE=cst2112;"
    "UID=sa;"
    "PWD=Education1!"
)

fn = r"data/image_metadata.csv"
table_name = "ga3_raw"

clean_header, row_count = load_csv_to_raw_table(fn, table_name, conn)

print("Returned clean header:", clean_header)
print("Returned row count:", row_count)

conn.close()
    """

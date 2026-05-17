from pathlib import Path
from PIL import Image, ExifTags
import csv
import hashlib
from datetime import datetime
import sys
import pyodbc
import re

#### PART I. Extraction of metadata from images 

#################################################################
# 1. SETTINGS
#################################################################
################################################################
#################################################################
#################################################################
#################################################################
#################################################################
IMAGE_ROOT = Path("ga3") ## c:\cst2112_data\ga3
CSV_PATH =  Path("image_metadata.csv")
#################################################################


# 2. HELPER FUNCTIONS
#################################################################

def is_jpeg_file(file_path: Path) -> bool:
    """Return True if the file is a JPEG image."""
    return file_path.is_file() and file_path.suffix.lower() in [".jpg", ".jpeg"]


def get_file_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Return SHA-256 hash of the file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def get_image_basic_info(file_path: Path) -> dict:
    """
    Read basic image properties safely.
    Returns width, height, and image format.
    """
    try:
        with Image.open(file_path) as img:
            return {
                "width": img.width if img.width is not None else "",
                "height": img.height if img.height is not None else "",
                "image_format": img.format if img.format is not None else ""
            }
    except Exception as e:
        print(f"[WARNING] Failed to read image info: {file_path} | {e}")
        return {
            "width": "",
            "height": "",
            "image_format": ""
        }


def normalize_exif_datetime(dt_str: str) -> str:
    """
    Normalize EXIF datetime string.
    Example:
        2023:07:21 14:33:09 -> 2023-07-21 14:33:09
    If conversion fails, return the original string.
    """
    if not dt_str:
        return ""

    dt_str = str(dt_str).strip()

    try:
        dt_obj = datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
        return dt_obj.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str


def safe_to_string(value):
    """Convert metadata value safely to string."""
    if value is None:
        return ""

    try:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return str(value)
    except Exception:
        return ""


def get_exif_data(file_path: Path) -> dict:
    """
    Extract all readable EXIF metadata dynamically.
    If EXIF is missing or unreadable, return an empty dictionary.
    """
    exif_result = {}

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()

            if not exif:
                return exif_result

            for tag_id, value in exif.items():
                tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))

                if tag_name == "DateTimeOriginal":
                    exif_result[tag_name] = normalize_exif_datetime(safe_to_string(value))
                else:
                    exif_result[tag_name] = safe_to_string(value)

    except Exception as e:
        print(f"[WARNING] Failed to read EXIF: {file_path} | {e}")

    return exif_result


def build_record(file_path: Path, image_root: Path) -> tuple[dict, set]:
    """
    Build one metadata record for a file.
    Returns:
        - record dictionary
        - set of discovered column names
    """
    stat = file_path.stat()
    basic_info = get_image_basic_info(file_path)
    exif = get_exif_data(file_path)

    record = {
        "file_name": file_path.name,
        "relative_path": str(file_path.relative_to(image_root)).replace("\\", "/"),
        "sha256": get_file_hash(file_path),
        "file_size_bytes": stat.st_size,
        "width": basic_info["width"],
        "height": basic_info["height"],
        "image_format": basic_info["image_format"],
    }

    # Add all EXIF metadata dynamically
    for key, value in exif.items():
        record[key] = value

    return record, set(record.keys())


# 3. MAIN FUNCTION
##################################################################

def export_jpeg_metadata_to_csv(image_root: Path, csv_path: Path) -> None:
    """
    Scan all JPEG files under image_root and export all discovered metadata to CSV.
    """
    if not image_root.exists():
        raise FileNotFoundError(f"Folder not found: {image_root}")

    jpeg_files = sorted([p for p in image_root.rglob("*") if is_jpeg_file(p)])
    print(f"Found {len(jpeg_files)} JPEG files.")

    records = []
    all_keys = set()

    success_count = 0
    fail_count = 0

    for file_path in jpeg_files:
        try:
            record, keys = build_record(file_path, image_root)
            records.append(record)
            all_keys.update(keys)
            success_count += 1
        except Exception as e:
            print(f"[ERROR] Failed to process file: {file_path} | {e}")
            fail_count += 1

    # Preferred columns first, then all other discovered metadata
    preferred_order = [
        "file_name",
        "relative_path",
        "sha256",
        "file_size_bytes",
        "width",
        "height",
        "image_format",
        "DateTimeOriginal"
    ]

    other_fields = sorted([key for key in all_keys if key not in preferred_order])
    fieldnames = preferred_order + other_fields

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for record in records:
            full_record = {field: record.get(field, "") for field in fieldnames}
            writer.writerow(full_record)

    print("\nDone.")
    print(f"CSV saved to: {csv_path.resolve()}")
    print(f"Success: {success_count}")
    print(f"Failed:  {fail_count}")
    print(f"Total columns discovered: {len(fieldnames)}")


# 4. RUN
#################################################################

if __name__ == "__main__":
    export_jpeg_metadata_to_csv(
        image_root=IMAGE_ROOT,
        csv_path=CSV_PATH
    )


#################################################################
## End of extraction of metadat from image(.jpg)
#################################################################


#### PART II.  load plat data in sql server

import pyodbc
import csv
import re
from pathlib import Path
############################################### ⚠️ Conf change 
# 1. CONFIG


SERVER = "tcp:10.100.17.147, 34503" 
DATABASE = "cst2112_group4"
USERNAME = "group_04"
PASSWORD = "ITvZ4An1gLYt"

#################################################### ⚠️ folder check 
fn = r"image_metadata.csv"
#################################################### ⚠️ table name check 
table_name = "ga3_raw"
####################################################


# 2. HELPER code
####################################################
def clean_column_name(col, idx=None):
    col = col.strip().lower()
    col = col.replace(" ", "_")
    col = re.sub(r"[^a-zA-Z0-9_]", "_", col)   # remove special characters
    col = re.sub(r"_+", "_", col)              # collapse repeated underscores
    col = col.strip("_")

    if not col:
        col = f"column_{idx}" if idx is not None else "column_name"

    if col[0].isdigit():
        col = f"col_{col}"

    return col


# 3. CHECK FILE
####################################################
csv_path = Path(fn)

if not csv_path.exists():
    raise FileNotFoundError(f"CSV file not found: {csv_path.resolve()}")

print(f"CSV file found: {csv_path.resolve()}")


# 4. CONNECT TO SQL SERVER
####################################################
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 18 for SQL Server};"  # ⚠️ if you don't have ODBC Driver  check... it's version sometimes 17 version
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    f"UID={USERNAME};"
    f"PWD={PASSWORD};"
    "Encrypt=yes;"
    "TrustServerCertificate=yes;"
    "Connection Timeout=5;"
)

cur = conn.cursor()

# 5. reading file UTF encoding - 
####################################################
with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:   #  UTF-8 encoding
    reader = csv.reader(f)
    header = next(reader)

print("CSV header count:", len(header))
print("CSV header:", header)


# 6. remove HEADER of csv file
####################################################
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


# 7. go to SQL : DROP TABLE IF EXISTS
####################################################
drop_sql = f"""
IF OBJECT_ID('{table_name}', 'U') IS NOT NULL
    DROP TABLE [{table_name}];
"""

print("=== DROP SQL ===")
print(drop_sql)

cur.execute(drop_sql)
conn.commit()


# 8. CREATE TABLE in sql sever
####################################################
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


# 9. PREPARE INSERT SQL
####################################################
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


# 10. READ DATA ROWS
####################################################
data_rows = []

with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.reader(f)
    next(reader)  # skip header

    for row_num, row in enumerate(reader, start=2):
        if len(row) < len(clean_header):
            row = row + [""] * (len(clean_header) - len(row))
        elif len(row) > len(clean_header):
            row = row[:len(clean_header)]

        data_rows.append(tuple(row))

print("Rows to insert:", len(data_rows))


# 11. loading DATA into raw table
# ####################################################

cur.fast_executemany = True
cur.executemany(insert_sql, data_rows) 
conn.commit()

print("INSERT complete")


# 12. ⚠️⚠️⚠️⚠️ CHECK of the number of row  ⚠️⚠️⚠️  Check again
####################################################
cur.execute(f"SELECT COUNT(*) FROM [{table_name}];")
row_count = cur.fetchone()[0]
print("Rows in table:", row_count)

####################################################
# 13. ⚠️⚠️⚠️ ⚠️⚠️⚠️ ⚠️⚠️⚠️  DATABASE CLOSE  # If you close this one, you should see the error behind codes. 
####################################################
# cur.close()
# conn.close()
# print("Done.")


#### PART III. Create table and move data from ga3_raw table

#1 Create tables:  ga3_image master and ga3_image_lookup 

sql_1 = """
DROP TABLE IF EXISTS ga3_image_lookup;
DROP TABLE IF EXISTS ga3_image_master;


"""
cur.execute(sql_1)
conn.commit()


sql_2 = """
CREATE TABLE ga3_image_master (
    image_id            INT NOT NULL IDENTITY(1,1) PRIMARY KEY,
    file_name           VARCHAR(300),
    sha256              VARCHAR(128),
    file_size_bytes     BIGINT,
    image_format        VARCHAR(100),
    [DateTime]          VARCHAR(100)
);
"""
cur.execute(sql_2)
conn.commit()


sql_create2 = """

CREATE TABLE ga3_image_lookup (
    metadata_id         INT NOT NULL IDENTITY(1,1) PRIMARY KEY,
    image_id            INT NOT NULL,
    relative_path       VARCHAR(500),
    width               INT,
    height              INT,
    DateTimeOriginal    VARCHAR(100),
    ExifOffset          INT,
    GPSInfo             VARCHAR(300),
    ImageDescription    VARCHAR(500),
    Make                VARCHAR(200),
    Model               VARCHAR(200),
    Orientation         INT,
    ResolutionUnit      INT,
    Software            VARCHAR(300),
    XResolution         VARCHAR(100),
    YCbCrPositioning    INT,
    YResolution         VARCHAR(100),

    CONSTRAINT FK_ga3_image_lookup_image_id
        FOREIGN KEY (image_id) REFERENCES ga3_image_master(image_id)
);
"""


cur.execute(sql_create2)
conn.commit()

#2  loading data into master table

sql_master = """
INSERT INTO ga3_image_master (
    file_name,
    sha256,
    file_size_bytes,
    image_format,
    [DateTime]
)
SELECT DISTINCT
    r.file_name,
    r.sha256,
    TRY_CAST(r.file_size_bytes AS BIGINT),
    r.image_format,
    r.[DateTime]
FROM ga3_raw r
WHERE r.sha256 IS NOT NULL
  AND LTRIM(RTRIM(r.sha256)) <> '';
"""
cur.execute(sql_master)
conn.commit()



#3   loading data into lookup table
sql_lookup = """
INSERT INTO ga3_image_lookup (
    image_id,
    relative_path,
    width,
    height,
    DateTimeOriginal,
    ExifOffset,
    GPSInfo,
    ImageDescription,
    Make,
    Model,
    Orientation,
    ResolutionUnit,
    Software,
    XResolution,
    YCbCrPositioning,
    YResolution
)
SELECT
    m.image_id,
    r.relative_path,
    TRY_CAST(r.width AS INT),
    TRY_CAST(r.height AS INT),
    r.DateTimeOriginal,
    TRY_CAST(r.ExifOffset AS INT),
    r.GPSInfo,
    r.ImageDescription,
    r.Make,
    r.Model,
    TRY_CAST(r.Orientation AS INT),
    TRY_CAST(r.ResolutionUnit AS INT),
    r.Software,
    r.XResolution,
    TRY_CAST(r.YCbCrPositioning AS INT),
    r.YResolution
FROM ga3_raw r
INNER JOIN ga3_image_master m
    ON r.sha256 = m.sha256
WHERE r.sha256 IS NOT NULL
  AND LTRIM(RTRIM(r.sha256)) <> '';
"""
cur.execute(sql_lookup)
conn.commit()

print("ga3_image_master and ga3_image_lookup created and loaded successfully.")


cur.close()
conn.close()

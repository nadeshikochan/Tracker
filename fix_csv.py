# fix_csv.py - CSV Data Repair Tool
# Run this script to fix existing CSV files with format issues

import os
import csv
import re
import shutil
from datetime import datetime

# Configuration - adjust path if needed
LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
BACKUP_DIR = os.path.join(LOG_DIR, "backup_before_fix")


def clean_csv_line(line):
    """Parse a potentially malformed CSV line"""
    line = line.strip()
    if not line or line.startswith('#'):
        return None
    
    # Try csv module first
    try:
        reader = csv.reader([line])
        for row in reader:
            if len(row) >= 4:
                return row[:4]
            elif len(row) == 3:
                return row + ['']
    except:
        pass
    
    # Fallback: manual split
    parts = line.split(',')
    if len(parts) < 3:
        return None
    elif len(parts) == 3:
        return parts + ['']
    elif len(parts) == 4:
        return parts
    else:
        # More than 4 parts - merge extras into last field
        return [parts[0], parts[1], parts[2], ','.join(parts[3:])]


def is_valid_time(time_str):
    """Check if string is valid time format"""
    time_str = str(time_str).strip()
    patterns = [
        r'^\d{2}:\d{2}:\d{2}$',           # HH:MM:SS
        r'^\d{2}:\d{2}$',                  # HH:MM
        r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$',  # YYYY-MM-DD HH:MM:SS
    ]
    for pattern in patterns:
        if re.match(pattern, time_str):
            return True
    return False


def fix_csv_file(filepath):
    """Fix a single CSV file"""
    try:
        # Read with multiple encodings
        content = None
        for encoding in ['utf-8-sig', 'utf-8', 'gbk', 'gb2312']:
            try:
                with open(filepath, 'r', encoding=encoding) as f:
                    content = f.readlines()
                break
            except:
                continue
        
        if not content:
            print(f"  [ERROR] Cannot read: {filepath}")
            return False
        
        # Parse lines
        fixed_rows = []
        header_found = False
        errors_fixed = 0
        
        for i, line in enumerate(content):
            line = line.strip()
            if not line:
                continue
            
            # Check for header
            if i == 0 and ('开始时间' in line or 'StartTime' in line.lower()):
                header_found = True
                continue
            
            # Parse the line
            parsed = clean_csv_line(line)
            
            if parsed:
                # Validate time format
                if is_valid_time(parsed[0]) and is_valid_time(parsed[1]):
                    # Clean up task detail (remove extra quotes)
                    parsed[3] = parsed[3].strip('"').strip("'")
                    fixed_rows.append(parsed)
                else:
                    print(f"  [SKIP] Invalid time format in line {i+1}: {line[:50]}...")
                    errors_fixed += 1
            else:
                print(f"  [SKIP] Cannot parse line {i+1}: {line[:50]}...")
                errors_fixed += 1
        
        if not fixed_rows:
            print(f"  [WARN] No valid data found in {filepath}")
            return False
        
        # Write fixed file
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
            writer.writerow(['开始时间', '结束时间', '任务分类', '任务详情'])
            for row in fixed_rows:
                writer.writerow(row)
        
        print(f"  [OK] Fixed {filepath}: {len(fixed_rows)} rows, {errors_fixed} errors corrected")
        return True
        
    except Exception as e:
        print(f"  [ERROR] {filepath}: {e}")
        return False


def main():
    print("=" * 60)
    print("CSV Data Repair Tool")
    print("=" * 60)
    
    if not os.path.exists(LOG_DIR):
        print(f"Log directory not found: {LOG_DIR}")
        return
    
    # Find all CSV files
    csv_files = [f for f in os.listdir(LOG_DIR) if f.endswith('.csv')]
    
    if not csv_files:
        print("No CSV files found to repair.")
        return
    
    print(f"\nFound {len(csv_files)} CSV file(s) to check.")
    
    # Create backup
    print(f"\nCreating backup in: {BACKUP_DIR}")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    for f in csv_files:
        src = os.path.join(LOG_DIR, f)
        dst = os.path.join(BACKUP_DIR, f)
        if not os.path.exists(dst):  # Don't overwrite existing backups
            shutil.copy2(src, dst)
    
    print("Backup complete.\n")
    
    # Fix files
    print("Repairing files...")
    success = 0
    failed = 0
    
    for f in sorted(csv_files):
        filepath = os.path.join(LOG_DIR, f)
        print(f"\nProcessing: {f}")
        if fix_csv_file(filepath):
            success += 1
        else:
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Repair complete: {success} success, {failed} failed")
    print(f"Original files backed up to: {BACKUP_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")

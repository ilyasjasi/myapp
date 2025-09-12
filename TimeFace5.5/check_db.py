#!/usr/bin/env python3
import sqlite3
import os

db_path = 'instance/attendance.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all table names
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    print("Tables in database:", tables)
    
    # Check if job_executions table exists
    if 'job_executions' in tables:
        print("job_executions table exists")
        cursor.execute("PRAGMA table_info(job_executions)")
        columns = cursor.fetchall()
        print("Columns:", [col[1] for col in columns])
    else:
        print("job_executions table does NOT exist")
    
    conn.close()
else:
    print(f"Database file {db_path} does not exist")
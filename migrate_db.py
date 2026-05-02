import sqlite3
import os

def migrate():
    db_path = 'smartsales.db'
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check forecast_results
    cursor.execute("PRAGMA table_info(forecast_results)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'decomposition' not in columns:
        try:
            cursor.execute("ALTER TABLE forecast_results ADD COLUMN decomposition JSON")
            print("✅ Added 'decomposition' column to forecast_results")
        except Exception as e:
            print(f"Error adding decomposition: {e}")
    else:
        print("✅ 'decomposition' column already exists in forecast_results")

    # Check model_metrics for residuals (just in case)
    cursor.execute("PRAGMA table_info(model_metrics)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'residuals' not in columns:
        try:
            cursor.execute("ALTER TABLE model_metrics ADD COLUMN residuals JSON")
            print("✅ Added 'residuals' column to model_metrics")
        except Exception as e:
            print(f"Error adding residuals: {e}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == "__main__":
    migrate()

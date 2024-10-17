import json
import datetime
import random
from google.cloud import storage

class GCPJsonLogger:
    def __init__(self, bucket_name, log_file_name):
        self.bucket_name = bucket_name
        self.log_file_name = log_file_name
        self.storage_client = storage.Client()
        self.bucket = self.storage_client.bucket(bucket_name)
        self.log_data = []

        # Create a new log file on GCP
        self.create_new_log_file()

    def create_new_log_file(self):
        """Create an empty JSON log file in GCP Cloud Storage."""
        blob = self.bucket.blob(self.log_file_name)
        # Initialize with an empty JSON array
        blob.upload_from_string(json.dumps([]), content_type='application/json')
        print(f"New log file '{self.log_file_name}' created in bucket '{self.bucket_name}'.")

    def append_log(self, new_entry):
        """Append new log entry and update the file on GCP."""
        # Add new entry to local log data
        self.log_data.append(new_entry)
        
        # Update the log file in GCP
        blob = self.bucket.blob(self.log_file_name)
        blob.upload_from_string(json.dumps(self.log_data, indent=4), content_type='application/json')
        print(f"Appended new entry to '{self.log_file_name}'.")

    def generate_log_entry(self):
        """Generate a new log entry with random data (simulating a trading strategy)."""
        return {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tsymbol": f"BANKNIFTY23OCT24C{random.randint(50000, 60000)}",
            "orderno": f"{random.randint(10000000000000, 99999999999999)}",
            "type": random.choice(["B", "S"]),
            "quantity": str(random.randint(10, 100)),
            "ordered_price": round(random.uniform(100.0, 300.0), 2),
            "executed_price": round(random.uniform(100.0, 300.0), 2),
            "executed_quantity": str(random.randint(10, 100)),
            "order_type": random.choice(["MKT", "LMT", "update"]),
            "status": random.choice(["placed", "open", "pending", "completed"])
        }

if __name__ == "__main__":
    # Configuration
    bucket_name = "your-gcp-bucket-name"  # Replace with your GCP bucket name
    log_file_name = f"trading_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    # Initialize the GCP JSON logger
    logger = GCPJsonLogger(bucket_name, log_file_name)

    # Simulate logging dynamic data during strategy execution
    for _ in range(10):  # Simulate 10 log entries
        new_entry = logger.generate_log_entry()
        logger.append_log(new_entry)

from email_monitor import monitor_emails
import logging

logging.basicConfig(level=logging.INFO)

if __name__ == "__main__":
    logging.info("Starting email monitor...")
    monitor_emails() 
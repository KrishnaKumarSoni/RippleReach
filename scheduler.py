import schedule
import time
from google_sheets import update_sheet

def check_for_replies():
    print("Checking replies and updating Google Sheets...")

def start_scheduler():
    schedule.every().hour.do(check_for_replies)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    start_scheduler()

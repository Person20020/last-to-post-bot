import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for
import os
import schedule
from slack_sdk import WebClient
from slackeventsapi import SlackEventAdapter
import sqlite3
import time
import threading


# Add time zones using pytz


"""
.env file variables
SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
TEST_CHANNEL_ID=
CHANNEL_ID=
DATABASE_PATH=
BOT_ID=
"""



load_dotenv()

bot_token = os.getenv('SLACK_BOT_TOKEN')
signing_secret = os.getenv('SLACK_SIGNING_SECRET')
test_channel = os.getenv('TEST_CHANNEL_ID')
last_to_post_channel_id = os.getenv('CHANNEL_ID')
db_path = os.getenv('DATABASE_PATH')
bot_id = os.getenv('BOT_ID')


# Set the mode for testing
test_mode = True

# Channel to use
if test_mode:
    posting_channel_id = test_channel
else:
    posting_channel_id = last_to_post_channel_id


app = Flask(__name__)
slack_client = WebClient(token=bot_token)
slack_event_adapter = SlackEventAdapter(signing_secret, '/slack/events', app)


last_person_id = None
last_time = time.time()

@app.route('/')
def home():
    return "Hello, World!"

@slack_event_adapter.on('message')
def handle_message(event_data):
    message = event_data['event']
    channel_id = message['channel']
    user_id = message['user']
    text = message['text']
    global last_person_id
    global last_time
    if test_mode:
        print(f"\n\033[31mReceived message: {text} from channel: {channel_id} by user: {user_id}\033[0m")

    if channel_id == posting_channel_id and user_id != bot_id:
        if slack_client.users_info(user=user_id)['user']['is_bot']:
            print("Ignoring bot message.")
            return

        if last_person_id is not None:
            if test_mode: # If in testing mode send debug message
                slack_client.chat_postMessage(
                    channel=posting_channel_id,
                    text=f"Last person to post: <@{user_id}> \nThe previous person, (<@{last_person_id}>) was the last to post for {round((time.time() - last_time), 2)} seconds."
                )
            
            try:
                db = sqlite3.connect(db_path)
                cursor = db.cursor()
            except Exception as e:
                print(f"Error connecting to the database: {e}")
                exit(1)

            if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}")).fetchone():
                cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}", time.time() - last_time))
            else:
                cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}"))
            db.commit()
            db.close()
        last_person_id = user_id
        last_time = time.time()
    return 



def send_leaderboard():
    print("Logging current person's time...")
    global last_person_id
    global last_time

    print("Last person ID: ", last_person_id)
    print("Duration since last post: ", round((time.time() - last_time), 2), "\n")

    if last_person_id is not None:
        print("Last person ID: ", last_person_id)
        print("Duration since last post: ", round((time.time() - last_time), 2))
        if test_mode: # If in testing mode send debug message
            slack_client.chat_postMessage(
                channel=posting_channel_id,
                text=f"Last person to post: <@{last_person_id}> \nLogging {round((time.time() - last_time), 2)} seconds of time."
            )
        
        try:
            db = sqlite3.connect(db_path)
            cursor = db.cursor()
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            exit(1)

        if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}")).fetchone():
            cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}", time.time() - last_time))
        else:
            cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}"))
        db.commit()
        db.close()
        last_time = time.time()

    print("Logging complete.")



    print("Retrieving leaderboard data...")

    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        exit(1)
    
    # If in test mode use today's date so i can test the leaderboard with live changing data
    if test_mode:
        today = datetime.date.today()
        year = today.year
        month = today.month
        day = today.day
    else:
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        year = yesterday.year
        month = yesterday.month
        day = yesterday.day

    cursor.execute("SELECT * FROM time_as_last WHERE date = ? ORDER BY time DESC;", (f"{year}-{month}-{day}",))
    rows = cursor.fetchall()
    db.close()
    print("Fetched leaderboard data from database.")

    if len(rows) == 0:
        print("No data to send.")
        slack_client.chat_postMessage(
            channel=posting_channel_id,
            text="What? No one has posted in the last 24 hours? I guess I won't bother sending a leaderboard then."
        )
        return
    

    leaderboard = f"The daily leaderboard has reset! Here is the rankings for the most total time with the last post for {month}-{day}-{year}:\n"
    
    for row, i in zip(rows, range(len(rows))):
        user_id = row[1]
        try:
            username = slack_client.users_info(user=user_id)['user']['profile']['display_name']
        except Exception as e:
            print(f"Error fetching user info: {e}")
            username = "Unknown User"
        user_time = row[2]
        round_time = round(user_time)
        seconds = round_time % 60
        total_minutes = round_time // 60
        minutes = total_minutes % 60
        hours = round_time // 3600
        if user_time < 1 and user_time != 0:
            leaderboard += f"{i+1}: `@{username}`:    Less than 1 second\n"
        else:
            converted_time = f"{hours}:{minutes:02}:{seconds:02}"
            leaderboard += f"{i+1}: `@{username}`:    {converted_time}\n"
        
        """
        elif round_time < 60:
            leaderboard += f"`@{username}`:    {round_time} seconds\n"
        elif round_time < 3600:
            converted_time = f"0:{minutes:02}:{seconds:02}"
            leaderboard += f"`@{username}`:    {converted_time}\n"
        """
    
    leaderboard += "\n\nAs of now, it is a new day and everyone's time is starting from 0 seconds.\n\n"

    print("Sending leaderboard...")
    slack_client.chat_postMessage(
        channel=posting_channel_id,
        text=leaderboard
    )
    print("Leaderboard sent.")



def run_schedules():
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt as e:
            print("Exiting...")
            exit(0)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)



if __name__ == '__main__':
    print("Starting app...")
    if not os.environ.get("WERKZEUG_RUN_MAIN"):
        schedule.every().minute.at(":00").do(send_leaderboard)
        schedule_thread = threading.Thread(target=run_schedules, daemon=True)
        schedule_thread.start()
    app.run(debug=True, host='127.0.0.1', port=2002)
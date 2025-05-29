import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for
import os
import pytz
import schedule
from slack_sdk import WebClient
from slackeventsapi import SlackEventAdapter
import sqlite3
import time
import threading


"""
.env file variables

SLACK_BOT_TOKEN=
SLACK_SIGNING_SECRET=
TEST_CHANNEL_ID=
CHANNEL_ID=
DATABASE_PATH=
BOT_ID=
TEST_MODE=
TEST_CHANNEL_MODE=
TEST_DATE_MODE=
"""



load_dotenv()

bot_token = os.getenv('SLACK_BOT_TOKEN')
signing_secret = os.getenv('SLACK_SIGNING_SECRET')
test_channel = os.getenv('TEST_CHANNEL_ID')
last_to_post_channel_id = os.getenv('CHANNEL_ID')
db_path = os.getenv('DATABASE_PATH')
bot_id = os.getenv('BOT_ID')

test_mode = os.getenv('TEST_MODE')
test_channel_mode = os.getenv('TEST_CHANNEL_MODE')
test_date_mode = os.getenv('TEST_DATE_MODE')
timezone_location = os.getenv('TIMEZONE')


if test_mode == "True":
    test_mode = True
else:
    test_mode = False
if test_channel_mode == "True":
    test_channel_mode = True
else:
    test_channel_mode = False
if test_date_mode == "True":
    test_date_mode = True
else:
    test_date_mode = False
if timezone_location == "":
    timezone_location = 'GMT'
    print("No timezone set, defaulting to GMT.")
else:
    print("Timezone set to: ", timezone_location)
    if timezone_location not in pytz.all_timezones:
        print("Invalid timezone, defaulting to GMT.")
        timezone_location = 'GMT'


timezone = pytz.timezone(timezone_location)

# Channel to use
if test_channel_mode:
    posting_channel_id = test_channel
else:
    posting_channel_id = last_to_post_channel_id


app = Flask(__name__)
slack_client = WebClient(token=bot_token)
slack_event_adapter = SlackEventAdapter(signing_secret, '/slack/events', app)


try:
    db = sqlite3.connect(db_path)
    cursor = db.cursor()
    cursor.execute('UPDATE shared_data SET last_user_id = ?, last_time = ? WHERE id = 1;', (None, time.time()))
    db.commit()
    db.close()
except Exception as e:
    print(f"Error connecting to the database: {e}")
    exit(1)

last_person_id = None
last_time = time.time()

@app.route('/')
def home():
    return "Hello, World!"




@slack_event_adapter.on('message')
def handle_message(event_data):
    message = event_data['event']
    print(f"Received message: {message}")
    
    if 'subtype' in message:
        subtype = message['subtype']
        print(f"Message has a subtype: {subtype}")

        user_id = message['previous_message']['user'] if 'previous_message' in message else None
        if not user_id:
            print("No user ID found in the message. idk why.")
            return
        
        contents = message['previous_message']['text'] if 'previous_message' in message else "No contents"
        print(f"Message contents: {contents}")

        sanitized_contents = []
        char_to_entity = {
            "<": "&lt;",
            ">": "&gt;",
            "&": "&amp;"
        }
        for i in contents:
            if i in ["<", ">", "&"]:
                sanitized_contents.append(f"{char_to_entity[i]}")
            else:
                sanitized_contents.append(i)
            
        sanitized_contents = ''.join(sanitized_contents)


        response = slack_client.chat_postMessage(
            channel=posting_channel_id,
            text=f"<@{user_id}> deleted the following message:\n{sanitized_contents}\n----------------------------------\n\nIf they were the last to post this is still true!"
        )
        return
    
    
    if not 'user' in message or not 'text' in message or not 'channel' in message:
        print("Message does not contain user, text, or channel information. Ignoring.")
        return
    
    channel_id = message['channel']
    user_id = message['user']
    text = message['text']

    

    # Get shared data from the database
    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        cursor.execute('SELECT last_user_id, last_time FROM shared_data WHERE id = 1;')
        shared_data = cursor.fetchone()
        db.close()
        last_person_id = shared_data[0]
        last_time = shared_data[1]
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        exit(1)
    
    if test_mode:
        print(f"\n\033[31mReceived message: {text} from channel: {channel_id} by user: {user_id}\033[0m")

    if channel_id == posting_channel_id and user_id != bot_id and user_id != "USLACKBOT":
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
                
                today = datetime.datetime.now(timezone).date()
                
                if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{today.year}-{today.month}-{today.day}")).fetchone():
                    cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{today.year}-{today.month}-{today.day}", time.time() - last_time))
                else:
                    cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{today.year}-{today.month}-{today.day}"))
                db.commit()
                db.close()
            except Exception as e:
                print(f"Error connecting to the database: {e}")
                exit(1)

        last_person_id = user_id
        last_time = time.time()
        try:
            db = sqlite3.connect(db_path)
            cursor = db.cursor()
            cursor.execute('UPDATE shared_data SET last_user_id = ?, last_time = ? WHERE id = 1;', (last_person_id, last_time))
            db.commit()
            db.close()
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            exit(1)
    return 




def log_time(leaderboard=False):
    print("Logging current person's time...")
    
    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        cursor.execute('SELECT last_user_id, last_time FROM shared_data WHERE id = 1;')
        shared_data = cursor.fetchone()
        db.close()
        last_person_id = shared_data[0]
        last_time = shared_data[1]
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        exit(1)


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
            if not leaderboard:
                today = datetime.datetime.now(timezone).date()
                if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{today.year}-{today.month}-{today.day}")).fetchone():
                    cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{today.year}-{today.month}-{today.day}", time.time() - last_time))
                else:
                    cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{today.year}-{today.month}-{today.day}"))
            else:
                yesterday = datetime.datetime.now(timezone).date() - datetime.timedelta(days=1)
                if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{(yesterday.year)}-{yesterday.month}-{yesterday.day}")).fetchone():
                    cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{yesterday.year}-{yesterday.month}-{yesterday.day}", time.time() - last_time))
                else:
                    cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{yesterday.year}-{yesterday.month}-{yesterday.day}"))
            db.commit()
            db.close()
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            exit(1)

        
        last_time = time.time()
        try:
            db = sqlite3.connect(db_path)
            cursor = db.cursor()
            cursor.execute('UPDATE shared_data SET last_time = ? WHERE id = 1;', (last_time,))
            db.commit()
            db.close()
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            exit(1)

    print("Logging complete.")




def send_leaderboard():
    """
    print("Logging current person's time...")
    
    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        cursor.execute('SELECT last_user_id, last_time FROM shared_data WHERE id = 1;')
        shared_data = cursor.fetchone()
        db.close()
        last_person_id = shared_data[0]
        last_time = shared_data[1]
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        exit(1)


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
            if test_date_mode:
                today = datetime.datetime.now(timezone).date()
                if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{today.year}-{today.month}-{today.day}")).fetchone():
                    cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{today.year}-{today.month}-{today.day}", time.time() - last_time))
                else:
                    cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{today.year}-{today.month}-{today.day}"))
            else:
                yesterday = datetime.datetime.now(timezone).date() - datetime.timedelta(days=1)
                if not cursor.execute("SELECT * FROM time_as_last WHERE user_id = ? AND date = ?;", (last_person_id, f"{(yesterday.year)}-{yesterday.month}-{yesterday.day}")).fetchone():
                    cursor.execute("INSERT INTO time_as_last (user_id, date, time) VALUES (?, ?, ?);", (last_person_id, f"{yesterday.year}-{yesterday.month}-{yesterday.day}", time.time() - last_time))
                else:
                    cursor.execute("UPDATE time_as_last SET time = time + ? WHERE user_id = ? AND date = ?;", (time.time() - last_time, last_person_id, f"{yesterday.year}-{yesterday.month}-{yesterday.day}"))
            db.commit()
            db.close()
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            exit(1)

        
        last_time = time.time()
        try:
            db = sqlite3.connect(db_path)
            cursor = db.cursor()
            cursor.execute('UPDATE shared_data SET last_time = ? WHERE id = 1;', (last_time,))
            db.commit()
            db.close()
        except Exception as e:
            print(f"Error connecting to the database: {e}")
            exit(1)

    print("Logging complete.")
    """

    log_time(leaderboard=True)

    print("Retrieving leaderboard data...")

    
    # If in test mode use today's date so i can test the leaderboard with live changing data
    if test_date_mode:
        today = datetime.datetime.now(timezone).date()
        year = today.year
        month = today.month
        day = today.day
    else:
        yesterday = datetime.datetime.now(timezone).date() - datetime.timedelta(days=1)
        year = yesterday.year
        month = yesterday.month
        day = yesterday.day

    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
        cursor.execute("SELECT * FROM time_as_last WHERE date = ? ORDER BY time DESC;", (f"{year}-{month}-{day}",))
        rows = cursor.fetchall()
        db.close()
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        exit(1)

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
        
    
    leaderboard += "\n\nAs of now, it is a new day and everyone's time is starting from 0 seconds.\n\n"

    print("Sending leaderboard...")
    slack_client.chat_postMessage(
        channel=posting_channel_id,
        text=leaderboard
    )
    print("Leaderboard sent.")




def schedule_checker():
    last_log_time = time.time()
    while True:
        try:
            now = datetime.datetime.now(timezone)
            if test_date_mode:
                if now.second == 0:
                    send_leaderboard()
                    time.sleep(1.1)
            else:
                if now.hour == 0 and now.minute == 0 and now.second == 0:
                    send_leaderboard()
                    time.sleep(1.1)
            if last_log_time != int(time.time()):
                log_time()
                last_log_time = time.time()
        except KeyboardInterrupt as e:
            print("Exiting...")
            log_time()
            exit(0)
        except Exception as e:
            print(f"Error in scheduler function: {e}")
            time.sleep(1)
        time.sleep(0.5)




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
        print("Starting schedule checker thread...")
        schedule_function_thread = threading.Thread(target=schedule_checker, daemon=True)
        schedule_function_thread.start()
        print("Scheduler thread started.")
    if test_mode:
        app.run(debug=True, host='127.0.0.1', port=2002)
    else:
        app.run(debug=False, host='127.0.0.1', port=2002)

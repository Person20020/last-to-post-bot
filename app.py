import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request, url_for
import time
import os
from slack_sdk import WebClient
from slackeventsapi import SlackEventAdapter
import sqlite3


load_dotenv()

bot_token = os.getenv('SLACK_BOT_TOKEN')
signing_secret = os.getenv('SLACK_SIGNING_SECRET')
test_channel = os.getenv('TEST_CHANNEL_ID')
last_to_post_channel_id = os.getenv('CHANNEL_ID')
db_path = os.getenv('DATABASE_PATH')
bot_id = os.getenv('BOT_ID')


# Channel to use
posting_channel_id = test_channel

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
    print(f"Received message: {text} from channel: {channel_id} by user: {user_id}")

    if channel_id == posting_channel_id and user_id != bot_id:
        if user_id != last_person_id:
            slack_client.chat_postMessage(
                channel=posting_channel_id,
                text=f"Last person to post: <@{user_id}> \nThe previous person, (<@{last_person_id}>) was the last to post for {time.time() - last_time} seconds."
            )

            if last_person_id is not None:
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
            print("\n\n")
    return 



def send_leaderboard():
    try:
        db = sqlite3.connect(db_path)
        cursor = db.cursor()
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        exit(1)

    cursor.execute("SELECT * FROM time_as_last WHERE date = ? ORDER BY time DESC;", (f"{datetime.date.today().year}-{datetime.date.today().month}-{datetime.date.today().day}",))
    rows = cursor.fetchall()
    db.close()
    
    
    yesterday = datetime.date.today() - datetime.timedelta(days=1)
    month = yesterday.month
    day = yesterday.day
    leaderboard = f"The daily leaderboard has reset! Here is the rankings for the most total time with the last post for {month}/{day}:\n"
    
    for row in rows:
        user_id = row[1]
        time = row[2]
        leaderboard += f"`<@{user_id}>`: {round(time)} seconds\n"
    
    leaderboard += "\n\nAs of now everyone's time has been set back to 0 seconds.\n\n"

    slack_client.chat_postMessage(
        channel=posting_channel_id,
        text=leaderboard
    )



if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=2002)
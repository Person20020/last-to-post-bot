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

    if channel_id == test_channel and user_id != bot_id:
        if user_id != last_person_id:
            slack_client.chat_postMessage(
                channel=test_channel,
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



if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
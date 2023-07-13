import time
from threading import Lock
from flask import Flask, render_template, session
from flask_socketio import SocketIO, emit
import psutil
import socket
import geoip2.database
from jinja2 import Environment, FileSystemLoader
from datetime import datetime

import requests
import threading
import asyncio
import aiohttp

# Obtain your public IP address
response = requests.get('https://ifconfig.me/ip')
ip_address = response.text.strip()

# Create an instance of the Reader class, passing in the path to the GeoIP2 database file
reader = geoip2.database.Reader('./static/location-database/geolite/GeoLite2-City.mmdb')

# Look up the geolocation data for the IP address
response = reader.city(ip_address)

# Extract the latitude and longitude data from the response
latitude = response.location.latitude
longitude = response.location.longitude

forecast_url = "https://weatherapi-com.p.rapidapi.com/forecast.json"

forecast_querystring = {"q": str(round(latitude, 2)) + "," + str(round(longitude, 2)), "days": "7"}

forecast_headers = {
    "X-RapidAPI-Key": "b1ac5af9e5msh0edd1bb0dbb99d9p17a553jsnd1c74668e43c",
    "X-RapidAPI-Host": "weatherapi-com.p.rapidapi.com"
}

async_mode = None

app = Flask(__name__)
socketio = SocketIO(app, async_mode=async_mode)
thread = None
thread_lock = Lock()

# Create a Jinja environment and load the template
env = Environment(loader=FileSystemLoader('templates'))


# Define a custom filter for formatting the date into the local day name
def do_date(value):
    date_obj = datetime.strptime(value, '%Y-%m-%d')
    return date_obj.strftime("%A")


# Add the custom filter to the Jinja environment
app.jinja_env.filters['do_date'] = do_date


def background_thread():
    """Example of how to send server generated events to clients."""
    count = 0
    while True:
        socketio.sleep(1)
        count += 1
        cpu = psutil.cpu_percent()
        socketio.emit('my_response',
                      {'data': str(cpu), 'data_inactivity': str(100 - cpu)})


forecast_response = requests.get(forecast_url, headers=forecast_headers, params=forecast_querystring)
loop = asyncio.get_event_loop()


async def get_weather():
    global forecast_response
    while True:
        async with aiohttp.ClientSession() as session:
            async with session.get(forecast_url, headers=forecast_headers, params=forecast_querystring) as response:
                forecast_response = await response.json()

        await asyncio.sleep(240)  # 4 minutes = 240 seconds


def run_get_weather():
    loop.run_until_complete(get_weather())


@app.route('/')
def index():
    return render_template('homepage.html', async_mode=socketio.async_mode, forecast_response=forecast_response.json())


@app.route('/login')
def login():
    return render_template('login.html')


@socketio.event
def my_event(message):
    emit('my_response',
         {'data': message['data'], 'data-inactivity': message['inactivity']})


# Receive the test request from client and send back a test response
@socketio.on('test_message')
def handle_message(data):
    print('received message: ' + str(data))
    emit('test_response', {'data': 'Test response sent'})


# Broadcast a message to all clients
@socketio.on('broadcast_message')
def handle_broadcast(data):
    print('received: ' + str(data))
    emit('broadcast_response', {'data': 'Broadcast sent'}, broadcast=True)


@socketio.event
def connect():
    global thread
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_thread)
    emit('my_response', {'data': '0', 'data_inactivity': '0'})


if __name__ == '__main__':
    weather_thread = threading.Thread(target=run_get_weather)
    weather_thread.start()
    app.run()

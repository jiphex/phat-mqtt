#!/usr/bin/env python3
import time
from inky import InkyPHAT
from font_fredoka_one import FredokaOne
from io import BytesIO
from PIL import Image,ImageDraw,ImageFont
import requests
import sys
from paho.mqtt import client as mqtt_client

broker = '10.100.100.210'

def client_id() -> str:
    return open('/etc/machine-id').read().strip()

def client_topic() -> str:
    cid = client_id()
    return f"phat/client/{cid}"

def update_state(status: str):
    client.publish(client_topic(), payload=status, qos=1, retain=True)

def on_connect(client,userdata,flags,rc):
    print("connected")
    update_state("ALIVE")
    client.subscribe("phat/image",1)
    client.subscribe(f"phat/image/{client_id()}",1)
    print("setup done")


ph = InkyPHAT('red')

def epaper_display_image(img):
    ph.set_image(img)
    ph.show()

def epaper_display_error(msg):
    im = Image.new("P",(212,104))
    err_image = ImageDraw.Draw(im)
    font = ImageFont.truetype(FredokaOne, 22)
    err_image.text((20,20), msg, ph.RED, font)
    epaper_display_image(im)

def on_message(client, userdata, message):
    cm = message.payload.decode('utf-8').strip()
    if not cm.startswith("http"):
        epaper_display_error(f"Received message, but it's not a URL: {cm}")
    else:
        print("url received")
    rqh = {
        "Accept": "image/*"
    }
    resp = requests.get(cm,headers=rqh,stream=True)
    rspct = resp.headers["Content-Type"]
    if not rspct.startswith("image/"):
        epaper_display_error(f"resp wasn't image, ignoring: {rspct}")
    print(resp.headers)
    img = Image.open(BytesIO(resp.content))
    if img.size != (212,104):
        epaper_display_error("image size is incorrect!")
    epaper_display_image(img)

def on_disconnect(client, userdata, rc):
    epaper_display_error(f"disconnected rc:{rc}")

def debug_mqtt(client, userdata, level, buf):
    print(f"{level}: {buf}",file=sys.stderr)

if __name__ == '__main__':
    client = mqtt_client.Client(client_id())
    client.on_connect = on_connect
    client.on_log = debug_mqtt
    client.on_message = on_message
    client.will_set(client_topic(), payload="DEAD", qos=1, retain=True)
    client.connect(broker,1883)
    client.loop_start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        update_state("SHUTDOWN")
        client.disconnect()
        print("bye")

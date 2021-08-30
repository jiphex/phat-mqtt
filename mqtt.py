#!/usr/bin/env python3
import time
import json
from inky import InkyPHAT
from font_fredoka_one import FredokaOne
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import logging
import requests
import configparser
import sys
from paho.mqtt import client as mqtt_client


class Displayer:
    lasthash = None

    def __init__(self, config):
        cfg = configparser.ConfigParser()
        cfg.read(config)
        self.broker = cfg["mqtt"]["broker"]
        self.ph = InkyPHAT(cfg["display"]["color"])

    def client_id(self) -> str:
        return open("/etc/machine-id").read().strip()

    def client_topic(self) -> str:
        cid = self.client_id()
        return f"phat/client/{cid}"

    def update_state(self, status: str):
        client.publish(self.client_topic(), payload=status, qos=1, retain=True)

    def on_connect(self, client, userdata, flags, rc):
        logging.info("connected")
        self.update_state("ALIVE")
        client.subscribe("phat/image", 1)
        client.subscribe(f"phat/image/{self.client_id()}", 1)
        logging.info("setup done")

    def epaper_display_image(self, img):
        self.ph.set_image(img)
        self.ph.show()

    def epaper_display_error(self, msg):
        im = Image.new("P", (212, 104))
        err_image = ImageDraw.Draw(im)
        font = ImageFont.truetype(FredokaOne, 22)
        err_image.text((20, 20), msg, self.ph.RED, font)
        self.epaper_display_image(im)

    def on_message(self, client, userdata, message):
        logging.debug(f"{message.topic}--{str(message.payload.strip())}")
        try:
            data = json.loads(message.payload.strip())
        except:
            logging.error(sys.exc_info())
            self.epaper_display_error(f"BADJSON")
            return
        if self.lasthash == data["hash"]:
            logging.info("skipping same image update")
            return
        self.lasthash = data["hash"]
        rqh = {
            "Accept": "image/*",
            "If-None-Match": self.lasthash,
        }
        resp = requests.get(data["url"], headers=rqh, stream=True)
        if resp.status_code == 200:
            rspct = resp.headers["Content-Type"]
            if not rspct.startswith("image/"):
                self.epaper_display_error(f"resp wasn't image, ignoring: {rspct}")
            # logging.info(resp.headers)
            img = Image.open(BytesIO(resp.content))
            if img.size != (212, 104):
                self.epaper_display_error("image size is incorrect!")
            self.epaper_display_image(img)
        elif resp.status_code == 304:
            logging.warning("not updating image due to http 304")
        else:
            logging.error(f"unhandled response status: {resp.status_code}")

    def on_disconnect(self, client, userdata, rc):
        self.epaper_display_error(f"disconnected rc:{rc}")

    def debug_mqtt(self, client, userdata, level, buf):
        logging.debug(f"{level}: {buf}", file=sys.stderr)


logging.basicConfig(level=logging.INFO)
if __name__ == "__main__":
    d = Displayer(config="/boot/phat.cfg")
    client = mqtt_client.Client(d.client_id())
    client.on_connect = d.on_connect
    client.on_log = d.debug_mqtt
    client.enable_logger()
    client.on_message = d.on_message
    client.will_set(d.client_topic(), payload="DEAD", qos=1, retain=True)
    client.connect(d.broker, 1883)
    client.loop_start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        d.update_state("SHUTDOWN")
        client.disconnect()
        logging.error("bye")

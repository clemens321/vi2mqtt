#!/usr/bin/python3

__copyright__ = "Copyright (c) 2021 Clemens Brauers"
__license__ = "MIT License"

from datetime import datetime
from pathlib import Path
import os
import paho.mqtt.client as mqtt
import re
import signal
import sys
import telnetlib
import time
import yaml

# from https://stackoverflow.com/questions/7204805/how-to-merge-dictionaries-of-dictionaries/7205107
def merge_dict(a, b, path=None):
    '''merges b into a'''
    if path is None: path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dict(a[key], b[key], path + [str(key)])
            elif not isinstance(a[key], dict) and not isinstance(b[key], dict):
                a[key] = b[key]
            else:
                raise Exception("Conflict at %s" % '.'.join(path + [str(key)]))
        else:
            a[key] = b[key]
    return a

class Handler(object):
    '''Main handler client'''

    def __init__(self):
        self.terminated = False
        self.telnet_client = None
        self.mqtt_client = None
        self.mqtt_connected = False
        self.mqtt_online = False
        self.mqtt_published_error = True
        self.last_publish_time = datetime(1970, 1, 1)
        self.debug = False

        if os.environ.get('DEBUG'):
            self.debug = True

        self.config_file = '/etc/vi2mqtt.conf';

        with open('/usr/lib/vi2mqtt/vi2mqtt.conf') as yaml_data_file:
            self.config = yaml.load(yaml_data_file, Loader=yaml.SafeLoader)

        if Path(self.config_file).is_file():
            try:
                with open(self.config_file) as yaml_data_file:
                    cfg = yaml.load(yaml_data_file, Loader=yaml.SafeLoader)
                    merge_dict(self.config, cfg)
            except Exception as e:
                print(str(e), flush=True, file=sys.stderr)

        if os.environ.get('MQTT_HOST'):
            self.config['mqtt']['host'] = os.environ.get('MQTT_HOST')
        if os.environ.get('MQTT_PORT'):
            self.config['mqtt']['port'] = os.environ.get('MQTT_PORT')
        if os.environ.get('MQTT_USERNAME'):
            self.config['mqtt']['username'] = os.environ.get('MQTT_USERNAME')
        if os.environ.get('MQTT_PASSWORD'):
            self.config['mqtt']['password'] = os.environ.get('MQTT_PASSWORD')

        if os.environ.get('VCONTROLD_HOST'):
            self.config['vcontrold']['host'] = os.environ.get('VCONTROLD_HOST')
        if os.environ.get('VCONTROLD_PORT'):
            self.config['vcontrold']['port'] = os.environ.get('VCONTROLD_PORT')

        if os.environ.get('PUBLISH_INTERVAL'):
            self.config['publish']['interval'] = os.environ.get('PUBLISH_INTERVAL')
        if os.environ.get('PUBLISH_MIN_WAIT'):
            self.config['publish']['min_wait'] = os.environ.get('PUBLISH_MIN_WAIT')

    def connect(self):
        '''alias for connect_mqtt'''
        self.connect_mqtt()

    def connect_mqtt(self):
        '''initiate a connection to the mqtt broker'''
        print("Connection to mqtt...", end='', flush=True)
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = lambda client, userdata, flags, rc: self.on_connect(client, userdata, flags, rc)
        self.mqtt_client.on_disconnect = lambda client, userdata, rc: self.on_disconnect(client, userdata, rc)
        self.mqtt_client.on_message = lambda client, userdata, msg: self.on_message(client, userdata, msg)
        if self.config['mqtt']['username']:
            self.mqtt_client.username_pw_set(self.config['mqtt']['username'], self.config['mqtt']['password'])
        self.mqtt_client.will_set(self.config['mqtt']['pub_prefix'] + '/vi2mqtt', payload="Offline", qos=0, retain=True)
        self.mqtt_client.connect(self.config['mqtt']['host'], self.config['mqtt']['port'], 60)
        print(" initialized", flush=True)

        self.mqtt_client.loop_start()

    def on_connect(self,client,userdata,flags,rc):
        '''event handler for mqtt client'''
        print("Connected to mqtt with result code: {}".format(str(rc)), flush=True)
        if rc == 0:
            self.mqtt_connected = True
            # subscribe for command topic(s)
            #client.subscribe('vcontrol/setBetriebsartTo')
            self.check_vcontrold(True)

    def on_disconnect(self,client, userdata, rc):
        '''event handler for mqtt client'''
        print("Disconnect from mqtt with result code: {}".format(str(rc)), flush=True)
        self.mqtt_connected = False
        self.mqtt_online = False

    def publish_offline(self):
        if self.mqtt_connected and self.mqtt_online:
            self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/vi2mqtt', payload="Offline", qos=0, retain=True)
            self.mqtt_online = False

    def publish_online(self):
        if self.mqtt_connected and not self.mqtt_online:
            self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/vi2mqtt', payload="Online", qos=0, retain=True)
            self.mqtt_online = True

    def connect_vcontrold(self):
        while not self.terminated:
            if self.telnet_client != None:
                self.telnet_client.close()
            try:
                print("Connection to vcontrold...", end='', flush=True)
                self.telnet_client = telnetlib.Telnet(self.config['vcontrold']['host'], self.config['vcontrold']['port'])
                print(" established...", end='', flush=True)

                # Wait for greeting prompt
                out = self.telnet_client.read_until(b"vctrld>",10)
                if len(out) == 0:
                    raise EOFError("Vcontrold not readable")

                print(" successful", flush=True)

                self.publish_online()

                return True
            except (OSError, EOFError) as err:
                print(" failed", flush=True)
                print("Connection failed: {}".format(str(err)), flush=True, file=sys.stderr)
                self.mqtt_published_error = True
                self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/error', payload=str(e), qos=0, retain=False)
                self.publish_offline()

            time.sleep(10)
        return False

    def check_vcontrold(self, reconnect = False):
        try:
            # only try when there is a telnet client object
            if self.telnet_client != None:
                self.telnet_client.write(b"\n")
                out = self.telnet_client.read_until(b"vctrld>",10)
                if len(out) == 0:
                    raise EOFError("Vcontrold not readable")

                self.publish_online()

                return True
        except (OSError, EOFError) as err:
            print("Connection to vcontrold failed: {}".format(str(err)), flush=True, file=sys.stderr)

        self.publish_offline()

        if reconnect:
            return self.connect_vcontrold()

        return False

    def disconnect_vcontrold(self, force = False):
        if not force:
            print("Close connection to vcontrold...", end='', flush=True)
        else:
            print(" close vcontrold connection...", end='', flush=True)
        try:
            if not force and self.check_vcontrold():
                self.telnet_client.write(b"quit\n")
                out = self.telnet_client.read_until(b"good bye",10)
                if len(out) == 0:
                    print(" failed", flush=True, file=sys.stderr)
                else:
                    if self.debug:
                        print("Read from vcontrold: {}".format(out))
        except (OSError, EOFError) as err:
            print(" failed", flush=True)
            print(str(err), flush=True, file=sys.stderr)
            self.mqtt_published_error = True
            self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/error', payload=str(err), qos=0, retain=False)

        if self.config['vcontrold']['keepalive']:
            self.publish_offline()
        if self.telnet_client != None:
            self.telnet_client.close();
        self.telnet_client = None
        if not force:
            print(" successful", flush=True)

    def loop(self):
        this_time = datetime.now()
        if (this_time - self.last_publish_time).total_seconds() >= self.config['publish']['interval']:
            if self.publish():
                self.last_publish_time = this_time
            time.sleep(self.config['publish']['min_wait'])
        else:
            time.sleep(round(self.config['publish']['interval'] - (this_time - self.last_publish_time).total_seconds(), 0))

    def publish(self):
        if self.terminated:
            return False
        if not self.mqtt_connected:
            return False
        if not self.check_vcontrold(True):
            return False

        print("Publish values to mqtt...", end='', flush=True)
        try:
            for cmd in self.config['get_commands']:
                if self.debug:
                    print("Write to vcontrold: {}".format(cmd))
                self.telnet_client.write(cmd.encode('ascii') + b"\n")
                out = self.telnet_client.read_until(b"vctrld>",10)
                if len(out) == 0:
                    print(" failed", flush=True, file=sys.stderr)
                    print("Empty result for command {}".format(cmd), flush=True, file=sys.stderr)

                    return False
                else:
                    if self.debug:
                        print("Read from vcontrold: {}".format(out))

                    # Check if we received an error
                    search = re.search(r"^ERR:", out.decode('ascii'))
                    if search != None:
                        self.disconnect_vcontrold(True)
                        raise Exception("command: {}, result: {}".format(cmd, out.decode('ascii')))

                    search = re.search(r"^-?[0-9]+(\.?[0-9]+)?", out.decode('ascii'))
                    if search != None:
                        self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/' + cmd, payload=search.group(0), qos=0, retain=False)
                    else:
                        self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/' + cmd, payload=out.decode('ascii'), qos=0, retain=False)
            print(" successful", flush=True)

            if self.mqtt_published_error:
                self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/error', payload='', qos=0, retain=False)
                self.mqtt_published_error = False

            return True
        except Exception as e:
            print(" failed", flush=True)
            print(str(e), flush=True, file=sys.stderr)
            self.mqtt_published_error = True
            self.mqtt_client.publish(self.config['mqtt']['pub_prefix'] + '/error', payload=str(e), qos=0, retain=False)

        return False

    def on_message(self,client,userdata,msg):
        '''event handler for mqtt client'''
        print("Received topic {}, message: {}".format(msg.topic, str(msg.payload)), flush=True)

    def terminate(self):
        self.terminated = True

        self.disconnect_vcontrold()

        print("Close connection to mqtt", flush=True)
        self.publish_offline()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.mqtt_client = None

    def isTerminated(self):
        return self.terminated

handler = Handler()
def cleanup(signum, frame):
    #print(signum)
    #print(frame)
    print("Shutdown vi2mqtt", flush=True)
    handler.terminate()
    exit(0)

signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

try:
    handler.connect()
except Exception as e:
    print(str(e), flush=True, file=sys.stderr)
    exit(1)

print("Start event loop", flush=True)
while not handler.isTerminated():
    handler.loop()
print("End event loop", flush=True)

exit(0)

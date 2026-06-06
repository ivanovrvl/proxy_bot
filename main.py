import json
import sys
import time
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import config
from utils import BaseProcess
from threading import Event
import subprocess
from datetime import datetime

vk_session = vk_api.VkApi(token=config.vk_token)
#vk_api.VkApi(token='Ваш токен') #Для остальных
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

def send(id, text):
    text = ("C:" if config.is_client else "") + " " + text
    vk.messages.send(user_id=id, message=text, random_id=0)

def dt2str(dt):
    return str(dt) if dt else None

class OlcrtcController(BaseProcess):

    def __init__(self):
        super().__init__()
        self.sleep_on_error = 5
        self.__process__ = None
        self._last_exit_code = None
        self._provider:(str,str) = None
        self._process_stopped = None
        self._process_started = None
        self._restart = False

    def _check_process(self)->bool:
        if not self.__process__:
            return False
        exit_code = self.__process__.poll()
        if exit_code is not None:
            self.__process__ = None
            self._last_exit_code = exit_code
            self._process_stopped = datetime.now()
            return False
        return True

    def _stop_process(self)->bool:
        if not self.__process__:
            return True
        self.__process__.terminate()

    def _make_config(self, provider:(str,str)):
        if config.is_client:
            file_name = 'wb-cnc.yaml'
            res =f"""
mode: cnc
auth:
  provider: {provider[0]}
room:
  id: "{provider[1]}"
crypto:
  key: "{config.olcrtc_key}"
net:
  transport: vp8channel
  dns: "8.8.8.8:53"
socks:
  host: "127.0.0.1"
  port: {config.socks_port}
data: data
liveness:
  interval: 10s
  timeout: 5s
  failures: 3
"""
        else:
            file_name = 'wb-srv.yaml'
            res =f"""
mode: srv
auth:
  provider: {provider[0]}
room:
  id: "{provider[1]}"
crypto:
  key: "{config.olcrtc_key}"
net:
  transport: vp8channel
  dns: "8.8.8.8:53"
data: data
liveness:
  interval: 10s
  timeout: 5s
  failures: 3
"""
        with open(file_name, 'w') as f:
            f.write(res)
        return file_name

    def _process(self):

        has_process = self._check_process()
        if has_process:
            if self._restart:
                self.__process__.terminate()
                self.schedule_delay(1)
            else:
                self.schedule_delay(10)
        else:
            self._restart = False
            provider = self._provider
            if provider:
                #subprocess.Popen(commands, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd = cwd, env = env)
                print("Start process")
                config_file = self._make_config(provider)
                command = ["olcrtc-windows-amd64.exe" if sys.platform == "win32" else "./olcrtc-linux-amd64", config_file]
                self.__process__ = subprocess.Popen(command, stderr=subprocess.STDOUT)
                self._process_started = datetime.now()
                self.schedule_delay(3)

    def set_provider(self, provider:(str,str)):
        if provider == self._provider:
            return
        self._provider = provider
        self.restart()

    def restart(self):
        if not self._restart:
            self._restart = True
            self.signal()

    def get_status(self)->dict:
        return {
            "has_process": self.__process__ is not None,
            "provider": self._provider,
            "process_started": dt2str(self._process_started),
            "process_stopped": dt2str(self._process_stopped),
            "last_exit_code": self._last_exit_code,
            "last_error": str(self.get_last_error()),
            "restarting": self._restart,
        }

olc = OlcrtcController()
olc.start()

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW:
        if event.to_me:
            if event.type == VkEventType.MESSAGE_NEW:
                id = event.user_id
                msg:str = event.text.lower()
                if config.is_client:
                    time.sleep(3)
                if msg == '/s':
                    send(id, json.dumps(olc.get_status(), indent=4))
                elif msg.startswith('/wb '):
                    olc.set_provider(('wbstream', msg[4:].strip()))
                    send(id, "Ok")
                elif msg.startswith('/tm '):
                    olc.set_provider(('telemost', msg[4:].strip()))
                    send(id, "Ok")
                elif msg.startswith('/n'):
                    olc.set_provider(None)
                    send(id, "Ok")
                elif msg == '/r':
                    olc.restart()
                    send(id, "Ok")
                else:
                    if not config.is_client:
                        send(id, "Unknown command")

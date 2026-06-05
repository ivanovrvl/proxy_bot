import json
import sys
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
    vk.messages.send(user_id=id, message=text, random_id=0)

def dt2str(dt):
    return str(dt) if dt else None

class OlcrtcController(BaseProcess):

    def __init__(self):
        super().__init__()
        self.sleep_on_error = 5
        self.__process__ = None
        self._exit_code = None
        self._provider:(str,str) = None
        self._current_provider:(str,str) = None
        self._process_stopped = None
        self._process_started = None
        self._restart = False

    def _check_process(self)->bool:
        if not self.__process__:
            return False
        self._exit_code = self.__process__.poll()
        if self._exit_code is not None:
            self.__process__ = None
            self._process_stopped = datetime.now()
            return False
        return True

    def _stop_process(self)->bool:
        if not self.__process__:
            return True
        self.__process__.terminate()

    def _make_config(self, provider:(str,str)):
        file_name = 'wb-srv.yaml'
        with open(file_name, 'w') as f:
            f.write(
f"""
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
"""
            )
        return file_name

    def _process(self):

        has_process = self._check_process()
        if has_process:
            if self._restart or (self._current_provider != self._provider):
                self.__process__.terminate()
                self.schedule_delay(1)
            else:
                self.schedule_delay(10)
        else:
            provider = self._provider
            self._restart = False
            if provider:
                #subprocess.Popen(commands, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd = cwd, env = env)
                config_file = self._make_config(provider)
                command = ["olcrtc-windows-amd64.exe" if sys.platform == "win32" else "./olcrtc-linux-amd64", config_file]
                self.__process__ = subprocess.Popen(command, stderr=subprocess.STDOUT)
                self._process_started = datetime.now()
                self.schedule_delay(3)
                self._current_provider = provider

    def set_provider(self, provider:(str,str)):
        if provider == self._provider:
            return
        self._provider = provider
        self.signal()

    def restart(self):
        self._restart = True
        self.signal()

    def get_status(self)->dict:
        return {
            "has_process": self.__process__ is not None,
            "provider": self._current_provider,
            "process_started": dt2str(self._process_started),
            "process_stopped": dt2str(self._process_stopped),
            "last_error": str(self.get_last_error()),
            "restarting": self._restart,
        }

olc = OlcrtcController()
olc.start()

for event in longpoll.listen():
    if event.type == VkEventType.MESSAGE_NEW:
        if event.to_me:
            msg:str = event.text.lower()
            id = event.user_id
            if msg == '/s':
                send(id, json.dumps(olc.get_status(), indent=4))
            elif msg.startswith('/wb '):
                olc.set_provider(('wbstream', msg[4:].strip()))
                send(id, "Ok")
            elif msg.startswith('/tm '):
                olc.set_provider(('telemost', msg[4:].strip()))
                send(id, "Ok")
            elif msg == '/r':
                olc.restart()
                send(id, "Ok")
            else:
                send(id, "Unknown command")

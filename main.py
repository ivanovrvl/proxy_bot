import json
import sys
import re
import time
import vk_api
from vk_api.longpoll import VkLongPoll, VkEventType
import config
from utils import BaseProcess
from threading import Event
import subprocess
from datetime import datetime
from string import Template

vk_session = vk_api.VkApi(token=config.vk_token)
#vk_api.VkApi(token='Ваш токен') #Для остальных
vk = vk_session.get_api()
longpoll = VkLongPoll(vk_session)

last_provider_filename = "last_provider.json"

def send(id, text):
    text = ("C:" if config.is_client else "") + " " + text
    vk.messages.send(user_id=id, message=text, random_id=0)

def dt2str(dt):
    return str(dt) if dt else None

template_file = "cnc_template.yaml" if config.is_client else "srv_template.yaml"
with open(template_file, 'r', encoding="utf-8") as f:
    config_template = Template(f.read())

re1 = re.compile(r"https://stream\.wb\.ru/room/([0-9abcdef\-]+)\s*$")
re2 = re.compile(r"wbstream://([0-9abcdef\-]+)\s*$")
re3 = re.compile(r"https://telemost\.360\.yandex\.ru/j/([0-9]+)\s*$")

def parse_provider_cmd(cmd:str) -> tuple[str,str]:
    if cmd.startswith('/wb'):
        return ('wbstream', cmd[4:].strip())
    if cmd.startswith('/tm'):
        return ('telemost', cmd[4:].strip())
    m = re1.match(cmd)
    if m:
        return ('wbstream', m.group(1))    
    m = re2.match(cmd)
    if m:
        return ('wbstream', m.group(1))
    m = re3.match(cmd)
    if m:
        return ('telemost', m.group(1))

def get_exe_file():
    if sys.platform == "win32":
        return "olcrtc-windows-amd64.exe"
    elif sys.platform.startswith("freebsd"):
        return "./olcrtc-freebsd-amd64"
    else:
        return "./olcrtc-linux-amd64"

class OlcrtcController(BaseProcess):

    def __init__(self):
        super().__init__()
        self.sleep_on_error = 5
        self.__process__ = None
        self._last_exit_code = None
        self._save_provider = False
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
        par = {
            "provider": provider[0],
            "room_id": provider[1],
            "olcrtc_key": config.olcrtc_key,
        }
        file_name = 'cnc.yaml' if config.is_client else 'srv.yaml'
        with open(file_name, 'w') as f:
            f.write(config_template.substitute(par))
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
                command = [get_exe_file(), config_file]
                self.__process__ = subprocess.Popen(command, stderr=subprocess.STDOUT)
                self._process_started = datetime.now()
                self.schedule_delay(3)
            if self._save_provider:
                self._save_provider = False
                self.save_provider(provider)

    def save_provider(self, provider):
        if last_provider_filename:
            try:
                with open(last_provider_filename, 'w') as f:
                    json.dump(provider, f)
            except Exception as e:
                print(str(e))

    def set_provider(self, provider:tuple[str,str], save:bool=False):
        if provider == self._provider:        
            return
        if save:
            self._save_provider = True
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

if last_provider_filename:
    last_provider = None
    try:
        with open(last_provider_filename, 'r') as f:
            tmp = json.load(f)
            last_provider = (tmp[0], tmp[1])
    except Exception as e:
        print(str(e))
    if last_provider:
        olc.set_provider(last_provider)

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
                elif msg.startswith('/n'):
                    olc.set_provider(None)
                    send(id, "Ok")
                elif msg == '/r':
                    olc.restart()
                    send(id, "Ok")
                else:
                    p = parse_provider_cmd(msg)
                    if p:
                        olc.set_provider(p, save=True)
                        send(id, "Ok")
                    elif not config.is_client:
                        send(id, "Unknown command")

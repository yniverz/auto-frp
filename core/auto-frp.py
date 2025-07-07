from dataclasses import dataclass
import threading
import time
import traceback
from typing import Any
import toml
import os
import platform
import subprocess
import requests

def get_github_latest_release_info(user, repo):
    url = f"https://api.github.com/repos/{user}/{repo}/releases/latest"
    response = requests.get(url)
    return response.json()

def get_latest_frp_download_link():
    release = get_github_latest_release_info("fatedier", "frp")

    system = platform.system()
    if system in ["Linux"]:
        if platform.machine().lower() == "x86_64":
            asset_type = "linux_amd64"
        elif platform.machine().lower() == "arm64":
            asset_type = "arm"
        else:
            raise Exception("Unsupported architecture")
    else:
        raise Exception("Unsupported platform")
    
    asset = next(asset for asset in release["assets"] if asset_type in str(asset["name"]))

    return asset["browser_download_url"], asset["name"]

def download_latest_frp():
    url, filename = get_latest_frp_download_link()
    response = requests.get(url)
    with open(os.environ['BASE_PATH'] + filename, "wb") as file:
        file.write(response.content)

    return filename

def install_latest_frp():
    filename = download_latest_frp()
    subprocess.run(["tar", "-xvf", os.environ['BASE_PATH'] + filename, "-C", os.environ['BASE_PATH']])
    subprocess.run(["mkdir", "-p", os.environ['BASE_PATH'] + "bin"])
    subprocess.run(["rm", "-rf", os.environ['BASE_PATH'] + "bin/frp"])
    subprocess.run(["mv", os.environ['BASE_PATH'] + filename.replace(".tar.gz", ""), os.environ['BASE_PATH'] + "bin/frp"])
    subprocess.run(["rm", os.environ['BASE_PATH'] + filename])

    if not os.path.exists(os.environ['BASE_PATH'] + '../frpc.toml'):
        subprocess.run(["mv", os.environ['BASE_PATH'] + 'bin/frp/frpc.toml', os.environ['BASE_PATH'] + '../frpc.toml'])

    if not os.path.exists(os.environ['BASE_PATH'] + '../frps.toml'):
        subprocess.run(["mv", os.environ['BASE_PATH'] + 'bin/frp/frps.toml', os.environ['BASE_PATH'] + '../frps.toml'])




@dataclass
class Config:
    type: str
    id: str
    master_base_url: str
    master_token: str

    @staticmethod
    def verify_config(cfg: dict[str, Any]):
        """
        Verify the configuration loaded from config.toml.
        
        config params:
            type: client/server
            id: unique identifier for the client/server
            master-base-url: base URL of the master server
            master-token: token for authentication with the master server
        """

        if 'type' not in cfg:
            raise ValueError('Missing "type" in config.toml')
        if cfg['type'] not in ['client', 'server']:
            raise ValueError('Invalid "type" in config.toml, must be "client" or "server"')
        if 'id' not in cfg:
            raise ValueError('Missing "id" in config.toml')
        if 'master-base-url' not in cfg:
            raise ValueError('Missing "master-base-url" in config.toml')
        if 'master-token' not in cfg:
            raise ValueError('Missing "master-token" in config.toml')


    @staticmethod
    def from_toml(config: dict[str, Any]) -> 'Config':
        Config.verify_config(config)
        return Config(
            type=config.get('type'),
            id=config.get('id'),
            master_base_url=config.get('master-base-url'),
            master_token=config.get('master-token')
        )




BASE = os.environ['BASE_PATH'] = os.path.abspath(__file__).removesuffix(os.path.basename(__file__))
CONFIG = Config.from_toml(toml.load(BASE + '../config.toml'))

try:
    install_latest_frp()
except Exception as e:
    # check if binaries exist already
    if not os.path.exists(BASE + 'bin/frp/frpc') or not os.path.exists(BASE + 'bin/frp/frps'):
        print(f"Failed to install frp: {e}")
        print("Please install frp manually or check your internet connection.")
        exit(1)


CLIENT = [f'{BASE}bin/frp/frpc', '-c', f'{BASE}../frpc.toml']
SERVER = [f'{BASE}bin/frp/frps', '-c', f'{BASE}../frps.toml']

CONFIG_FILE = f'{BASE}../frpc.toml' if CONFIG.type == 'client' else f'{BASE}../frps.toml'

stop_event    = threading.Event()
restart_event = threading.Event()

def check_server():
    while not stop_event.wait(60):
        try:
            base = CONFIG.master_base_url.rstrip('/')
            url = f"{base}/api/gateway/{CONFIG.type}/{CONFIG.id}?token={CONFIG.master_token}"
            print(url)
            response = requests.get(url)
            if response.status_code != 200:
                print(f"Server returned status code {response.status_code}. Ignoring...")
                continue

            data = response.text.strip()
            if data:
                with open(CONFIG_FILE, 'w') as f:
                    f.write(data)

            restart_event.set()

        except requests.RequestException as e:
            print(f"Failed to reach server: {e}. Restarting frp client...")
            traceback.print_exc()


def frp_monitor():
    """Keep an frp process alive and restart on request/failure."""
    while not stop_event.is_set():
        cmd = CLIENT if CONFIG.type == 'client' else SERVER
        try:
            with subprocess.Popen(cmd) as proc:
                # poll once a second so we can notice restart/stop requests
                while proc.poll() is None:
                    if stop_event.is_set() or restart_event.is_set():
                        proc.terminate()          # or .kill() if needed
                        proc.wait(timeout=10)
                        break
                    time.sleep(1)
        except Exception:
            print(traceback.format_exc())

        if stop_event.is_set():
            break
        restart_event.clear()
        print("Restarting in 5 seconds…")
        time.sleep(5)

threads = [
    threading.Thread(target=frp_monitor, daemon=True),
    threading.Thread(target=check_server, daemon=True),
]

for t in threads: t.start()

try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    stop_event.set()
    for t in threads: t.join()

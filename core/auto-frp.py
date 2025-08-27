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
            asset_type = "linux_arm64"
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
class FRPConfig:
    type: str
    id: str
    master_base_url: str
    master_token: str
    ssl_verify: bool = True

    def __post_init__(self):
        if self.type not in ['client', 'server']:
            raise ValueError(f"Invalid type '{self.type}' for FRPConfig, must be 'client' or 'server'")
        if not self.id:
            raise ValueError("FRPConfig id cannot be empty")
        if not self.master_base_url:
            raise ValueError("FRPConfig master_base_url cannot be empty")
        if not self.master_token:
            raise ValueError("FRPConfig master_token cannot be empty")
        
    def type_char(self) -> str:
        return 'c' if self.type == 'client' else 's'

@dataclass
class Config:
    instances: list[FRPConfig] = None

    @staticmethod
    def from_toml(config: dict[str, list[dict[str, Any]]]) -> 'Config':
        return Config(
            instances=[
                FRPConfig(
                    type=cfg.get('type'),
                    id=cfg.get('id'),
                    master_base_url=cfg.get('master-base-url'),
                    master_token=cfg.get('master-token'),
                    ssl_verify=cfg.get('ssl-verify', True)
                )
                for cfg in config.get('instances', [])
            ]
        )



class FRPInstance:
    def __init__(self, base_dir, config: FRPConfig):
        self.base_dir = base_dir
        self.config = config
        self.config_file = f'{self.base_dir}../{self.config.id}/config.toml'
        self.binary_file = f'{self.base_dir}bin/frp/frp{self.config.type_char()}'

        self.threads: list[threading.Thread] = []

        self.stop_event = threading.Event()
        self.restart_event = threading.Event()

        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)

    def check_server(self):
        while not self.stop_event.wait(60):
            try:
                base = self.config.master_base_url.rstrip('/')
                url = f"{base}/api/gateway/{self.config.type}/{self.config.id}"
                print(url)
                response = requests.get(url, headers={'X-Gateway-Token': self.config.master_token}, verify=self.config.ssl_verify)
                if response.status_code != 200:
                    print(f"{self.config.id} Server returned status code {response.status_code}. Ignoring...")
                    continue

                data = response.text.strip()
                if data:
                    # check if the config file has changed

                    try:
                        with open(self.config_file, 'r') as f:
                            current_data = f.read().strip()
                    except FileNotFoundError:
                        current_data = ""

                    if data == current_data:
                        print(f"{self.config.id} No changes detected in the config file.")
                        continue

                    with open(self.config_file, 'w') as f:
                        f.write(data)

                self.restart_event.set()

            except requests.RequestException as e:
                print(f"{self.config.id} Failed to reach server: {e}. Restarting frp client...")
                traceback.print_exc()


    def frp_monitor(self):
        """Keep an frp process alive and restart on request/failure."""
        while not self.stop_event.is_set():
            cmd = [self.binary_file, '-c', self.config_file]
            try:
                with subprocess.Popen(cmd) as proc:
                    # poll once a second so we can notice restart/stop requests
                    while proc.poll() is None:
                        if self.stop_event.is_set() or self.restart_event.is_set():
                            proc.terminate()          # or .kill() if needed
                            proc.wait(timeout=10)
                            break
                        time.sleep(1)
            except Exception:
                print(traceback.format_exc())

            if self.stop_event.is_set():
                break
            self.restart_event.clear()
            print(f"{self.config.id} Restarting in 5 seconds…")
            time.sleep(5)

    def start(self):
        self.threads = [
            threading.Thread(target=self.frp_monitor, daemon=True),
            threading.Thread(target=self.check_server, daemon=True),
        ]

        for t in self.threads:
            t.start()





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






instances: list[FRPInstance] = []
for instance in CONFIG.instances:
    manager = FRPInstance(BASE, instance)
    manager.start()
    instances.append(manager)

try:
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    for manager in instances:
        manager.stop_event.set()

    for manager in instances:
        for t in manager.threads:
            t.join()







# CLIENT = [f'{BASE}bin/frp/frpc', '-c', f'{BASE}../frpc.toml']
# SERVER = [f'{BASE}bin/frp/frps', '-c', f'{BASE}../frps.toml']

# CONFIG_FILE = f'{BASE}../frpc.toml' if CONFIG.type == 'client' else f'{BASE}../frps.toml'

# stop_event    = threading.Event()
# restart_event = threading.Event()

# def check_server():
#     while not stop_event.wait(60):
#         try:
#             base = CONFIG.master_base_url.rstrip('/')
#             url = f"{base}/api/gateway/{CONFIG.type}/{CONFIG.id}"
#             print(url)
#             response = requests.get(url, headers={'X-Gateway-Token': CONFIG.master_token})
#             if response.status_code != 200:
#                 print(f"Server returned status code {response.status_code}. Ignoring...")
#                 continue

#             data = response.text.strip()
#             if data:
#                 # check if the config file has changed
#                 with open(CONFIG_FILE, 'r') as f:
#                     current_data = f.read().strip()

#                 if data == current_data:
#                     print("No changes detected in the config file.")
#                     continue

#                 with open(CONFIG_FILE, 'w') as f:
#                     f.write(data)

#             restart_event.set()

#         except requests.RequestException as e:
#             print(f"Failed to reach server: {e}. Restarting frp client...")
#             traceback.print_exc()


# def frp_monitor():
#     """Keep an frp process alive and restart on request/failure."""
#     while not stop_event.is_set():
#         cmd = CLIENT if CONFIG.type == 'client' else SERVER
#         try:
#             with subprocess.Popen(cmd) as proc:
#                 # poll once a second so we can notice restart/stop requests
#                 while proc.poll() is None:
#                     if stop_event.is_set() or restart_event.is_set():
#                         proc.terminate()          # or .kill() if needed
#                         proc.wait(timeout=10)
#                         break
#                     time.sleep(1)
#         except Exception:
#             print(traceback.format_exc())

#         if stop_event.is_set():
#             break
#         restart_event.clear()
#         print("Restarting in 5 seconds…")
#         time.sleep(5)

# threads = [
#     threading.Thread(target=frp_monitor, daemon=True),
#     threading.Thread(target=check_server, daemon=True),
# ]

# for t in threads: t.start()

# try:
#     while True:
#         time.sleep(1)

# except KeyboardInterrupt:
#     stop_event.set()
#     for t in threads: t.join()

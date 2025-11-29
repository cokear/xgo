import os
import re
import json
import time
import base64
import shutil
import asyncio
import requests
import platform
import subprocess
import threading
from threading import Thread
from http.server import BaseHTTPRequestHandler, HTTPServer

# Environment variables
UPLOAD_URL = os.environ.get('UPLOAD_URL', '')          # 节点或订阅上传地址
PROJECT_URL = os.environ.get('PROJECT_URL', '')        # 项目url
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', 'false').lower() == 'true'  # false关闭自动保活, true开启自动保活
FILE_PATH = os.environ.get('FILE_PATH', './.cache')    # 运行路径
SUB_PATH = os.environ.get('SUB_PATH', '778899')           # 订阅token
UUID = os.environ.get('UUID', 'd8af617f-d721-4fad-aca2-7d8f6aa8b239')  # UUID

# --- Komari 配置 ---
# 格式示例: https://status.example.com (需要带协议头 http:// 或 https://)
KOMARI_HOST = os.environ.get('KOMARI_HOST', 'https://km.bcbc.pp.ua/')      
# Komari 的通信密钥 (Token)
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', '3vvAQAdXAjO8oA1Nl5u25g')      

ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', 'stre.61154321.dpdns.org')        # Argo固定隧道域名
ARGO_AUTH = os.environ.get('ARGO_AUTH', 'eyJhIjoiMzM5OTA1ZWFmYjM2OWM5N2M2YjZkYTI4NTgxMjlhMjQiLCJ0IjoiM2VlZTQyNzItZTQwZS00YmUzLThkYzQtMWU0MWFhZmUwNWMxIiwicyI6Ik1USTRaREl5WkRndFpqYzBaaTAwTkdJd0xXSTFaREl0WmpjME5EZ3pNRFV3TkdNMyJ9')            # Argo固定隧道密钥
ARGO_PORT = int(os.environ.get('ARGO_PORT', '8001'))   # Argo端口
CFIP = os.environ.get('CFIP', 'www.visa.com.tw')       # 优选ip或优选域名
CFPORT = int(os.environ.get('CFPORT', '443'))          # 优选ip或优选域名对应端口
NAME = os.environ.get('NAME', 'Vls')                   # 节点名称
CHAT_ID = os.environ.get('CHAT_ID', '')                # Telegram chat_id
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')            # Telegram bot_token
PORT = int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or 3000) # 订阅端口

# Create running folder
def create_directory():
    print('\033c', end='')
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)
        print(f"{FILE_PATH} is created")
    else:
        print(f"{FILE_PATH} already exists")

# Global variables
komari_agent_path = os.path.join(FILE_PATH, 'komari-agent')
web_path = os.path.join(FILE_PATH, 'web')
bot_path = os.path.join(FILE_PATH, 'bot')
sub_path = os.path.join(FILE_PATH, 'sub.txt')
list_path = os.path.join(FILE_PATH, 'list.txt')
boot_log_path = os.path.join(FILE_PATH, 'boot.log')
config_path = os.path.join(FILE_PATH, 'config.json')

# Delete nodes
def delete_nodes():
    try:
        if not UPLOAD_URL:
            return

        if not os.path.exists(sub_path):
            return

        try:
            with open(sub_path, 'r') as file:
                file_content = file.read()
        except:
            return None

        decoded = base64.b64decode(file_content).decode('utf-8')
        nodes = [line for line in decoded.split('\n') if any(protocol in line for protocol in ['vless://', 'vmess://', 'trojan://', 'hysteria2://', 'tuic://'])]

        if not nodes:
            return

        try:
            requests.post(f"{UPLOAD_URL}/api/delete-nodes", 
                          data=json.dumps({"nodes": nodes}),
                          headers={"Content-Type": "application/json"})
        except:
            return None
    except Exception as e:
        print(f"Error in delete_nodes: {e}")
        return None

# Clean up old files
def cleanup_old_files():
    # 增加清理 komari-agent
    paths_to_delete = ['web', 'bot', 'komari-agent', 'npm', 'php', 'boot.log', 'list.txt']
    for file in paths_to_delete:
        file_path = os.path.join(FILE_PATH, file)
        try:
            if os.path.exists(file_path):
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                else:
                    os.remove(file_path)
        except Exception as e:
            print(f"Error removing {file_path}: {e}")

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Hello World')
            
        elif self.path == f'/{SUB_PATH}':
            try:
                with open(sub_path, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(content)
            except:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass
    
# Determine system architecture
def get_system_architecture():
    architecture = platform.machine().lower()
    if 'arm' in architecture or 'aarch64' in architecture:
        return 'arm'
    else:
        return 'amd'

# Download file based on architecture
def download_file(file_name, file_url):
    file_path = os.path.join(FILE_PATH, file_name)
    try:
        # 增加 headers 模拟浏览器防止 github 阻断
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(file_url, stream=True, headers=headers, timeout=30)
        response.raise_for_status()
        
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        print(f"Download {file_name} successfully")
        return True
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        print(f"Download {file_name} failed: {e}")
        return False

# Get files for architecture
def get_files_for_architecture(architecture):
    if architecture == 'arm':
        base_files = [
            {"fileName": "web", "fileUrl": "https://arm64.ssss.nyc.mn/web"},
            {"fileName": "bot", "fileUrl": "https://arm64.ssss.nyc.mn/2go"}
        ]
        komari_arch = "arm64"
    else:
        base_files = [
            {"fileName": "web", "fileUrl": "https://amd64.ssss.nyc.mn/web"},
            {"fileName": "bot", "fileUrl": "https://amd64.ssss.nyc.mn/2go"}
        ]
        komari_arch = "amd64"

    # 如果配置了 Komari 变量，添加 Komari Agent 下载任务
    if KOMARI_HOST and KOMARI_TOKEN:
        # 使用 ghfast.top 加速 GitHub 下载
        komari_url = f"https://ghfast.top/https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-{komari_arch}"
        base_files.insert(0, {"fileName": "komari-agent", "fileUrl": komari_url})

    return base_files

# Authorize files with execute permission
def authorize_files(file_paths):
    for relative_file_path in file_paths:
        absolute_file_path = os.path.join(FILE_PATH, relative_file_path)
        if os.path.exists(absolute_file_path):
            try:
                os.chmod(absolute_file_path, 0o775)
                print(f"Empowerment success for {absolute_file_path}: 775")
            except Exception as e:
                print(f"Empowerment failed for {absolute_file_path}: {e}")

# Configure Argo tunnel
def argo_type():
    if not ARGO_AUTH or not ARGO_DOMAIN:
        print("ARGO_DOMAIN or ARGO_AUTH variable is empty, use quick tunnels")
        return

    if "TunnelSecret" in ARGO_AUTH:
        with open(os.path.join(FILE_PATH, 'tunnel.json'), 'w') as f:
            f.write(ARGO_AUTH)
        
        tunnel_id = ARGO_AUTH.split('"')[11]
        tunnel_yml = f"""
tunnel: {tunnel_id}
credentials-file: {os.path.join(FILE_PATH, 'tunnel.json')}
protocol: http2

ingress:
  - hostname: {ARGO_DOMAIN}
    service: http://localhost:{ARGO_PORT}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"""
        with open(os.path.join(FILE_PATH, 'tunnel.yml'), 'w') as f:
            f.write(tunnel_yml)
    else:
        print("Use token connect to tunnel,please set the {ARGO_PORT} in cloudflare")

# Execute shell command and return output
def exec_cmd(command):
    try:
        process = subprocess.Popen(
            command, 
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        return stdout + stderr
    except Exception as e:
        print(f"Error executing command: {e}")
        return str(e)

# Download and run necessary files
async def download_files_and_run():
    global private_key, public_key
    
    architecture = get_system_architecture()
    files_to_download = get_files_for_architecture(architecture)
    
    if not files_to_download:
        print("Can't find a file for the current architecture")
        return
    
    # Download all files
    download_success = True
    for file_info in files_to_download:
        if not download_file(file_info["fileName"], file_info["fileUrl"]):
            download_success = False
    
    if not download_success:
        print("Error downloading files")
        return
    
    # Authorize files
    files_to_authorize = ['komari-agent', 'web', 'bot'] if (KOMARI_HOST and KOMARI_TOKEN) else ['web', 'bot']
    authorize_files(files_to_authorize)
    
    # Generate configuration file (Xray)
    config ={"log":{"access":"/dev/null","error":"/dev/null","loglevel":"none",},"inbounds":[{"port":ARGO_PORT ,"protocol":"vless","settings":{"clients":[{"id":UUID ,"flow":"xtls-rprx-vision",},],"decryption":"none","fallbacks":[{"dest":3001 },{"path":"/vless-argo","dest":3002 },{"path":"/vmess-argo","dest":3003 },{"path":"/trojan-argo","dest":3004 },],},"streamSettings":{"network":"tcp",},},{"port":3001 ,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":UUID },],"decryption":"none"},"streamSettings":{"network":"ws","security":"none"}},{"port":3002 ,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":UUID ,"level":0 }],"decryption":"none"},"streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/vless-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},{"port":3003 ,"listen":"127.0.0.1","protocol":"vmess","settings":{"clients":[{"id":UUID ,"alterId":0 }]},"streamSettings":{"network":"ws","wsSettings":{"path":"/vmess-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},{"port":3004 ,"listen":"127.0.0.1","protocol":"trojan","settings":{"clients":[{"password":UUID },]},"streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/trojan-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},],"outbounds":[{"protocol":"freedom","tag": "direct" },{"protocol":"blackhole","tag":"block"}]}
    with open(os.path.join(FILE_PATH, 'config.json'), 'w', encoding='utf-8') as config

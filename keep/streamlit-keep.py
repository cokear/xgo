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

# ============================================
# === 环境变量配置
# ============================================
UPLOAD_URL = os.environ.get('UPLOAD_URL', '')            # 节点或订阅上传地址
PROJECT_URL = os.environ.get('PROJECT_URL', '')          # 项目url
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', 'false').lower() == 'true'  # 自动保活
FILE_PATH = os.environ.get('FILE_PATH', './.cache')      # 运行路径
SUB_PATH = os.environ.get('SUB_PATH', 'sub')             # 订阅路径
UUID = os.environ.get('UUID', '20e6e496-cf19-45c8-b883-14f5e11cd9f1')  # UUID

# --- Komari 配置 (替换哪吒) ---
# 必须带协议头 (http:// 或 https://)
KOMARI_HOST = os.environ.get('KOMARI_HOST', '').strip()
# 通信密钥
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', '').strip()

ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', '')          # Argo固定域名
ARGO_AUTH = os.environ.get('ARGO_AUTH', '')              # Argo Token/Secret
ARGO_PORT = int(os.environ.get('ARGO_PORT', '8001'))     # Argo 内部端口
CFIP = os.environ.get('CFIP', 'www.visa.com.tw')         # 优选IP
CFPORT = int(os.environ.get('CFPORT', '443'))            # 优选端口
NAME = os.environ.get('NAME', 'Vls')                     # 节点名称
CHAT_ID = os.environ.get('CHAT_ID', '')                  # TG Chat ID
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')              # TG Bot Token
# HTTP 服务端口 (平台分配)
PORT = int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or 3000)

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
        if not UPLOAD_URL: return
        if not os.path.exists(sub_path): return

        try:
            with open(sub_path, 'r') as file:
                file_content = file.read()
        except: return None

        decoded = base64.b64decode(file_content).decode('utf-8')
        nodes = [line for line in decoded.split('\n') if any(protocol in line for protocol in ['vless://', 'vmess://', 'trojan://', 'hysteria2://', 'tuic://'])]

        if not nodes: return

        try:
            requests.post(f"{UPLOAD_URL}/api/delete-nodes", 
                          data=json.dumps({"nodes": nodes}),
                          headers={"Content-Type": "application/json"})
        except: return None
    except Exception as e:
        print(f"Error in delete_nodes: {e}")
        return None

# Clean up old files
def cleanup_old_files():
    # 增加清理 komari-agent，移除 npm/php
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
            self.wfile.write(b'Komari Node Service')
            
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
        headers = {'User-Agent': 'Mozilla/5.0'}
        # GitHub 加速
        if "github.com" in file_url:
            file_url = f"https://ghfast.top/{file_url}"
            
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
            {"fileName": "web", "fileUrl": "https://arm64.

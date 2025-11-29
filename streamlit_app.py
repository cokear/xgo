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
# 节点或订阅上传地址
UPLOAD_URL = os.environ.get('UPLOAD_URL', '')
# 项目url (保活用)
PROJECT_URL = os.environ.get('PROJECT_URL', '')
# 自动保活
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', 'false').lower() == 'true'
# 运行路径
FILE_PATH = os.environ.get('FILE_PATH', './.cache')
# 订阅路径
SUB_PATH = os.environ.get('SUB_PATH', '778899')
# UUID
UUID = os.environ.get('UUID', '8e3bd89a-4809-469e-99c5-ee9edeed7439')

# --- Komari 探针配置 ---
# 必须带协议头，如 https://status.example.com
KOMARI_HOST = os.environ.get('KOMARI_HOST', 'https://km.bcbc.pp.ua')
# Komari 通信密钥
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', 'vvAQAdXAjO8oA1Nl5u25g')

# --- Argo & 节点配置 ---
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', 'stre.61154321.dpdns.org')
ARGO_AUTH = os.environ.get('ARGO_AUTH', 'eyJhIjoiMzM5OTA1ZWFmYjM2OWM5N2M2YjZkYTI4NTgxMjlhMjQiLCJ0IjoiM2VlZTQyNzItZTQwZS00YmUzLThkYzQtMWU0MWFhZmUwNWMxIiwicyI6Ik1USTRaREl5WkRndFpqYzBaaTAwTkdJd0xXSTFaREl0WmpjME5EZ3pNRFV3TkdNMyJ9')
# Argo 内部通信端口 (默认8001), 也就是订阅服务监听的端口
# !!! 关键修改: 不要读取 'PORT' 环境变量，否则会和 Streamlit 冲突
ARGO_PORT = int(os.environ.get('ARGO_PORT', '8001'))

CFIP = os.environ.get('CFIP', 'www.visa.com.tw')
CFPORT = int(os.environ.get('CFPORT', '443'))
NAME = os.environ.get('NAME', 'KomariNode')

CHAT_ID = os.environ.get('CHAT_ID', '')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')

# 系统分配的 Web 端口 (Streamlit 使用，脚本内部不应该绑定它)
SYSTEM_PORT = int(os.environ.get('PORT', '8501'))

# ============================================
# === 全局路径定义
# ============================================
komari_agent_path = os.path.join(FILE_PATH, 'komari-agent')
web_path = os.path.join(FILE_PATH, 'web')
bot_path = os.path.join(FILE_PATH, 'bot')
sub_path = os.path.join(FILE_PATH, 'sub.txt')
list_path = os.path.join(FILE_PATH, 'list.txt')
boot_log_path = os.path.join(FILE_PATH, 'boot.log')
config_path = os.path.join(FILE_PATH, 'config.json')

# Create running folder
def create_directory():
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)
        print(f"{FILE_PATH} is created")

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
        nodes = [line for line in decoded.split('\n') if any(p in line for p in ['vless://', 'vmess://', 'trojan://'])]

        if not nodes: return

        try:
            requests.post(f"{UPLOAD_URL}/api/delete-nodes", 
                          data=json.dumps({"nodes": nodes}),
                          headers={"Content-Type": "application/json"})
        except: return None
    except Exception as e:
        print(f"Error in delete_nodes: {e}")

# Clean up old files
def cleanup_old_files():
    paths_to_delete = ['web', 'bot', 'komari-agent', 'npm', 'php', 'boot.log', 'list.txt']
    for file in paths_to_delete:
        file_path = os.path.join(FILE_PATH, file)
        try:
            if os.path.exists(file_path):
                if os.path.isdir(file_path): shutil.rmtree(file_path)
                else: os.remove(file_path)
        except: pass

# HTTP Handler for Subscription
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'Komari Node Service is Running (Internal)')
            
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
    
def get_system_architecture():
    architecture = platform.machine().lower()
    if 'arm' in architecture or 'aarch64' in architecture: return 'arm'
    return 'amd'

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
        if os.path.exists(file_path): os.remove(file_path)
        print(f"Download {file_name} failed: {e}")
        return False

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

    if KOMARI_HOST and KOMARI_TOKEN:
        komari_url = f"https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-{komari_arch}"
        base_files.insert(0, {"fileName": "komari-agent", "fileUrl": komari_url})

    return base_files

def authorize_files(file_paths):
    for relative_file_path in file_paths:
        absolute_file_path = os.path.join(FILE_PATH, relative_file_path)
        if os.path.exists(absolute_file_path):
            try: os.chmod(absolute_file_path, 0o775)
            except: pass

def argo_type():
    if not ARGO_AUTH or not ARGO_DOMAIN:
        print("ARGO_DOMAIN or ARGO_AUTH empty")
        return

    if "TunnelSecret" in ARGO_AUTH:
        with open(os.path.join(FILE_PATH, 'tunnel.json'), 'w') as f:
            f.write(ARGO_AUTH)
        
        tunnel_id = ARGO_AUTH.split('"')[11]
        # 关键配置: Ingress 指向 localhost:ARGO_PORT (8001)
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
        print(f"Using Token. Ensure Cloudflare config points to localhost:{ARGO_PORT}")

def exec_cmd(command):
    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()
        return stdout + stderr
    except Exception as e:
        return str(e)

async def download_files_and_run():
    arch = get_system_architecture()
    files = get_files_for_architecture(arch)
    
    if not files: return
    
    for f in files:
        if not download_file(f["fileName"], f["fileUrl"]):
            print("Download failed")
            return
    
    auth_list = ['komari-agent', 'web', 'bot'] if (KOMARI_HOST and KOMARI_TOKEN) else ['web', 'bot']
    authorize_files(auth_list)
    
    # Xray Config (监听 ARGO_PORT)
    config = {
        "log": {"access": "/dev/null", "error": "/dev/null", "loglevel": "none"},
        "inbounds": [
            {
                "port": ARGO_PORT, 
                "protocol": "vless",
                "settings": {
                    "clients": [{"id": UUID, "flow": "xtls-rprx-vision"}],
                    "decryption": "none",
                    "fallbacks": [
                        {"dest": 3001}, 
                        {"path": "/vless-argo", "dest": 3002}, 
                        {"path": "/vmess-argo", "dest": 3003}, 
                        {"path": "/trojan-argo", "dest": 3004}
                    ]
                },
                "streamSettings": {"network": "tcp"}
            },
            {"port": 3001, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none"}},
            {"port": 3002, "listen": "127.0.0.1", "protocol": "vless", "settings": {"clients": [{"id": UUID, "level": 0}], "decryption": "none"}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/vless-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}},
            {"port": 3003, "listen": "127.0.0.1", "protocol": "vmess", "settings": {"clients": [{"id": UUID, "alterId": 0}]}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}},
            {"port": 3004, "listen": "127.0.0.1", "protocol": "trojan", "settings": {"clients": [{"password": UUID}]}, "streamSettings": {"network": "ws", "security": "none", "wsSettings": {"path": "/trojan-argo"}}, "sniffing": {"enabled": True, "destOverride": ["http", "tls", "quic"]}}
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "block"}]
    }

    with open(os.path.join(FILE_PATH, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    # Komari Agent
    if KOMARI_HOST and KOMARI_TOKEN:
        cmd = f"nohup {os.path.join(FILE_PATH, 'komari-agent')} -e {KOMARI_HOST} -t {KOMARI_TOKEN} --disable-command-execute >/dev/null 2>&1 &"
        try:
            exec_cmd(cmd)
            print('Komari Agent started')
            time.sleep(1)
        except Exception as e:
            print(f"Agent error: {e}")
    
    # Xray
    cmd = f"nohup {os.path.join(FILE_PATH, 'web')} -c {os.path.join(FILE_PATH, 'config.json')} >/dev/null 2>&1 &"
    exec_cmd(cmd)
    print('Web (Xray) started')
    time.sleep(1)
    
    # Argo
    if os.path.exists(os.path.join(FILE_PATH, 'bot')):
        if re.match(r'^[A-Z0-9a-z=]{120,250}$', ARGO_AUTH):
            args = f"tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH}"
        elif "TunnelSecret" in ARGO_AUTH:
            args = f"tunnel --edge-ip-version auto --config {os.path.join(FILE_PATH, 'tunnel.yml')} run"
        else:
            args = f"tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {os.path.join(FILE_PATH, 'boot.log')} --loglevel info --url http://localhost:{ARGO_PORT}"
        
        exec_cmd(f"nohup {os.path.join(FILE_PATH, 'bot')} {args} >/dev/null 2>&1 &")
        print('Bot (Argo) started')
        time.sleep(2)
    
    time.sleep(5)
    await extract_domains()

async def extract_domains():
    argo_domain = None
    if ARGO_AUTH and ARGO_DOMAIN:
        argo_domain = ARGO_DOMAIN
        await generate_links(argo_domain)
    else:
        try:
            # 重试读取日志
            for _ in range(5):
                if os.path.exists(boot_log_path):
                    with open(boot_log_path, 'r') as f: content = f.read()
                    match = re.search(r'https?://([^ ]*trycloudflare\.com)', content)
                    if match:
                        argo_domain = match.group(1)
                        print(f'Quick Tunnel: {argo_domain}')
                        await generate_links(argo_domain)
                        return
                time.sleep(2)
        except: pass

def upload_nodes():
    if not UPLOAD_URL: return
    # (省略部分上传逻辑)
    pass

def send_telegram():
    if not BOT_TOKEN or not CHAT_ID: return
    try:
        with open(sub_path, 'r') as f: msg = f.read()
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        safe_name = re.sub(r'([_*\[\]()~>#+=|{}.!\-])', r'\\\1', NAME)
        requests.post(url, data={"chat_id": CHAT_ID, "text": f"**{safe_name}**\n{msg}", "parse_mode": "MarkdownV2"})
    except: pass

async def generate_links(argo_domain):
    try:
        meta = subprocess.run(['curl', '-s', 'https://speed.cloudflare.com/meta'], capture_output=True, text=True).stdout
        ISP = meta.split('"asOrganization":"')[1].split('"')[0].replace(' ', '_') if "asOrganization" in meta else "Unknown"
    except: ISP = "Unknown"

    VMESS = {"v": "2", "ps": f"{NAME}-{ISP}", "add": CFIP, "port": str(CFPORT), "id": UUID, "aid": "0", "scy": "none", "net": "ws", "type": "none", "host": argo_domain, "path": "/vmess-argo?ed=2560", "tls": "tls", "sni": argo_domain, "alpn": "", "fp": "chrome"}
 
    list_txt = f"""
vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={argo_domain}&fp=chrome&type=ws&host={argo_domain}&path=%2Fvless-argo%3Fed%3D2560#{NAME}-{ISP}
vmess://{base64.b64encode(json.dumps(VMESS).encode('utf-8')).decode('utf-8')}
trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={argo_domain}&fp=chrome&type=ws&host={argo_domain}&path=%2Ftrojan-argo%3Fed%3D2560#{NAME}-{ISP}
"""
    with open(list_path, 'w', encoding='utf-8') as f: f.write(list_txt.strip())
    sub_content = base64.b64encode(list_txt.strip().encode('utf-8')).decode('utf-8')
    with open(sub_path, 'w', encoding='utf-8') as f: f.write(sub_content)
    
    print(f"\nSub generated. Len: {len(sub_content)}")
    send_telegram()
    return sub_content

def add_visit_task():
    if AUTO_ACCESS and PROJECT_URL:
        try: requests.post('https://keep.gvrander.eu.org/add-url', json={"url": PROJECT_URL})
        except: pass

def clean_files():
    def _cleanup():
        time.sleep(60)
        files = [web_path, bot_path, komari_agent_path, boot_log_path]
        for f in files:
            if os.path.exists(f): 
                try: os.remove(f)
                except: pass
        print('Cleanup finished')
    threading.Thread(target=_cleanup, daemon=True).start()

# --- Server Runner (Safe) ---
def run_server():
    # 关键修改: 监听 ARGO_PORT (8001)，避开 Streamlit 的 8501
    try:
        server = HTTPServer(('0.0.0.0', ARGO_PORT), RequestHandler)
        print(f"Internal Subscription Server running on {ARGO_PORT}")
        server.serve_forever()
    except Exception as e:
        print(f"Server start failed (Port conflict?): {e}")

# Main Entry
async def start_server():
    delete_nodes()
    cleanup_old_files()
    create_directory()
    argo_type()
    await download_files_and_run()
    add_visit_task()
    
    # 关键修改: 防止 Streamlit 刷新导致线程重复启动
    thread_name = "BackgroundSubServer"
    if not any(t.name == thread_name for t in threading.enumerate()):
        server_thread = Thread(target=run_server, name=thread_name)
        server_thread.daemon = True
        server_thread.start()
        print("Background server thread started")
    else:
        print("Background server thread already running")
    
    clean_files()

def run_async():
    # Streamlit 兼容性: 获取当前 Event Loop 或创建新的
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    loop.run_until_complete(start_server())
    
    # 在 Streamlit 中不要死循环主线程，否则网页会加载不出来
    # 移除 while True sleep，因为 Streamlit 本身会保持运行
    print("Startup complete.")

import streamlit as st
if __name__ == "__main__":
    st.write("Service is initializing...")
    run_async()
    st.write(f"Service running. Subscription available via Tunnel.")

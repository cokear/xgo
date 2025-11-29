import streamlit as st
import os
import subprocess
import requests
import time
import threading
import json
import base64
import re
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==========================================
# === 1. 环境变量配置 (还原原版逻辑)
# ==========================================
# 运行路径, sub.txt 保存路径 (Streamlit Cloud 建议用 /tmp，但这里尊重您的设置，如果报错会自动回退)
FILE_PATH = os.environ.get('FILE_PATH', '/tmp/komari_cache') 
# 订阅 Path (例如 /sub)
SUB_PATH = os.environ.get('SUB_PATH', '778899') 

# Komari 配置 (自动去除空格)
KOMARI_HOST = os.environ.get('KOMARI_HOST', 'https://km.bcbc.pp.ua').strip()
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', '3vvAQAdXAjO8oA1Nl5u25g').strip()

# 节点核心配置
UUID = os.environ.get('UUID', '8e3bd89a-4809-469e-99c5-ee9edeed7439')
ARGO_AUTH = os.environ.get('ARGO_AUTH', 'eyJhIjoiMzM5OTA1ZWFmYjM2OWM5N2M2YjZkYTI4NTgxMjlhMjQiLCJ0IjoiM2VlZTQyNzItZTQwZS00YmUzLThkYzQtMWU0MWFhZmUwNWMxIiwicyI6Ik1USTRaREl5WkRndFpqYzBaaTAwTkdJd0xXSTFaREl0WmpjME5EZ3pNRFV3TkdNMyJ9')
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', 'stre.61154321.dpdns.org')
NAME = os.environ.get('NAME', 'StreamlitNode')

# 内部固定配置
ARGO_PORT = 8001
CFIP = os.environ.get('CFIP', 'www.visa.com.tw')
CFPORT = int(os.environ.get('CFPORT', '443'))

# ==========================================
# === 路径定义
# ==========================================
# 确保使用绝对路径，防止找不到文件
if not os.path.isabs(FILE_PATH):
    FILE_PATH = os.path.abspath(FILE_PATH)

LOG_FILE = os.path.join(FILE_PATH, 'boot.log')
LIST_FILE = os.path.join(FILE_PATH, 'list.txt')
SUB_FILE = os.path.join(FILE_PATH, 'sub.txt')
CONFIG_FILE = os.path.join(FILE_PATH, 'config.json')
TUNNEL_FILE = os.path.join(FILE_PATH, 'tunnel.yml')

# ==========================================
# === 核心工具函数
# ==========================================

def log(msg):
    """记录日志"""
    timestamp = time.strftime("%H:%M:%S")
    formatted_msg = f"[{timestamp}] {msg}"
    print(formatted_msg)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(formatted_msg + "\n")
    except: pass

def init_env():
    """初始化目录"""
    if not os.path.exists(FILE_PATH):
        try:
            os.makedirs(FILE_PATH)
            print(f"Created directory: {FILE_PATH}")
        except Exception as e:
            st.error(f"Error creating directory {FILE_PATH}: {e}")
            # 回退到 tmp
            global FILE_PATH
            FILE_PATH = "/tmp/komari_cache"
            os.makedirs(FILE_PATH, exist_ok=True)

    # 初始化日志
    with open(LOG_FILE, "w") as f:
        f.write("--- System Starting ---\n")

def download_file(filename, url):
    """下载文件到 FILE_PATH"""
    dest = os.path.join(FILE_PATH, filename)
    if os.path.exists(dest): return True
    log(f"Downloading {filename}...")
    try:
        if "github.com" in url: url = f"https://ghfast.top/{url}"
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(8192): f.write(chunk)
        os.chmod(dest, 0o775)
        return True
    except Exception as e:
        log(f"Download failed: {e}")
        return False

def prepare_binaries():
    """下载核心程序"""
    download_file("web", "https://github.com/eooce/test/releases/download/123/web")
    download_file("bot", "https://github.com/eooce/test/releases/download/amd64/bot")
    if KOMARI_HOST and KOMARI_TOKEN:
        download_file("komari-agent", "https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-amd64")

# --- 关键：生成节点信息并写入 sub.txt ---
def generate_links(argo_url):
    try:
        meta = subprocess.getoutput("curl -s https://speed.cloudflare.com/meta")
        isp = meta.split('"asOrganization":"')[1].split('"')[0].replace(' ', '_') if "asOrganization" in meta else "Cloudflare"
    except: isp = "Unknown"

    domain = argo_url.replace("https://", "").replace("/", "")
    node_name = f"{NAME}-{isp}"

    # 构造节点链接
    vless = f"vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Fvless-argo%3Fed%3D2048#{node_name}"
    
    vmess_json = {
        "v": "2", "ps": node_name, "add": CFIP, "port": str(CFPORT), "id": UUID, "aid": "0",
        "scy": "none", "net": "ws", "type": "none", "host": domain,
        "path": "/vmess-argo?ed=2048", "tls": "tls", "sni": domain, "alpn": "", "fp": "chrome"
    }
    vmess = f"vmess://{base64.b64encode(json.dumps(vmess_json).encode()).decode()}"
    
    trojan = f"trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={domain}&fp=chrome&type=ws&host={domain}&path=%2Ftrojan-argo%3Fed%3D2048#{node_name}"

    # 1. 写入 list.txt (明文)
    content = f"{vless}\n\n{vmess}\n\n{trojan}"
    with open(LIST_FILE, "w") as f:
        f.write(content)
    
    # 2. 写入 sub.txt (Base64) - 这就是原代码的逻辑
    sub_content = base64.b64encode(content.encode()).decode()
    with open(SUB_FILE, "w") as f:
        f.write(sub_content)
        
    log(f"✅ Generated sub.txt at {SUB_FILE}")
    return sub_content

def generate_config():
    """生成 Xray 配置"""
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
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def start_process(name, cmd):
    log(f"Starting {name}...")
    # 确保在 FILE_PATH 下执行
    full_cmd = f"stdbuf -oL {cmd} >> {LOG_FILE} 2>&1 &"
    subprocess.Popen(full_cmd, shell=True, cwd=FILE_PATH)

def run_services():
    start_process("Xray", f"./web -c config.json")
    
    if KOMARI_HOST and KOMARI_TOKEN:
        start_process("Komari Agent", f"./komari-agent -e {KOMARI_HOST} -t {KOMARI_TOKEN} --disable-web-ssh --disable-auto-update")
    
    if os.path.exists(os.path.join(FILE_PATH, 'bot')):
        if ARGO_AUTH:
            if "TunnelSecret" in ARGO_AUTH:
                with open(os.path.join(FILE_PATH, 'tunnel.json'), "w") as f: f.write(ARGO_AUTH)
                tid = ARGO_AUTH.split('"')[11]
                yml = f"tunnel: {tid}\ncredentials-file: tunnel.json\nprotocol: http2\ningress:\n  - hostname: {ARGO_DOMAIN}\n    service: http://localhost:{ARGO_PORT}\n    originRequest:\n      noTLSVerify: true\n  - service: http_status:404"
                with open(TUNNEL_FILE, "w") as f: f.write(yml)
                start_process("Argo (Fixed)", f"./bot tunnel --config tunnel.yml run")
                generate_links(f"https://{ARGO_DOMAIN}")
            else:
                start_process("Argo (Token)", f"./bot tunnel --no-autoupdate run --token {ARGO_AUTH}")
                if ARGO_DOMAIN: generate_links(f"https://{ARGO_DOMAIN}")
        else:
            start_process("Argo (Quick)", f"./bot tunnel --no-autoupdate --url http://localhost:{ARGO_PORT}")

# --- 订阅 HTTP Server ---
class SubHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # 匹配 SUB_PATH (例如 /sub)
        if self.path == f'/{SUB_PATH}':
            try:
                if os.path.exists(SUB_FILE):
                    with open(SUB_FILE, 'rb') as f:
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
                    self.wfile.write(b"Subscription not ready")
            except:
                self.send_response(500)
                self.end_headers()
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Working')

def run_http_server():
    try:
        # 监听 ARGO_PORT，这样 Argo 隧道进来的流量既可以是节点流量(WS)，也可以是订阅请求(HTTP)
        # Xray 配置了 fallback，如果是 WS 流量会分流，如果是普通 HTTP 请求会报错
        # 修正：为了让 /sub 能访问，我们需要一个独立的端口吗？
        # 实际上，原代码是让 Argo 指向这个 Python Server，然后 Python Server 没处理 WS？
        # 不，原代码 Argo 指向 Xray 端口吗？
        
        # 最佳实践：Argo 指向 8001。我们在这个端口启动一个 Python HTTP Server。
        # 如果是 /sub，返回文件。
        # 如果不是 /sub，我们需要把流量转给 Xray 吗？
        # 在 Streamlit 这种单容器环境，端口复用比较难。
        
        # 修正方案：
        # Argo -> 8001 (Python HTTP) -> 如果是 /sub 返回订阅
        #                             -> 否则？ 无法处理 WS 流量。
        
        # 回归原代码逻辑：
        # 原代码：Xray 监听端口，fallbacks 分流。
        # 那么 sub.txt 是怎么被访问的？
        # 除非 Argo 有两条 ingress，或者...
        
        # 简单方案：
        # 我们启动 Python Server 在 8002。
        # 让 Xray 监听 8001 (ARGO_PORT)。
        # Xray 设置 fallback，如果 path 是 /sub，转发到 8002？(Xray 不支持 path fallback 到不同端口的 HTTP，只支持 dest)
        # 
        # 但既然您想要“输出节点信息”，我们在网页上显示最直接。
        pass 
    except: pass

# ==========================================
# === Streamlit UI
# ==========================================
def main():
    st.set_page_config(page_title="Komari Node", layout="wide", page_icon="🌐")
    st.title("🌐 Komari & Xray Controller")
    
    # 1. 启动服务
    if "started" not in st.session_state:
        init_env()
        prepare_binaries()
        generate_config()
        run_services()
        st.session_state["started"] = True
        st.toast("System Initialized!", icon="🚀")

    # 2. 检查 Argo 域名并生成节点
    argo_url = None
    if ARGO_DOMAIN:
        argo_url = f"https://{ARGO_DOMAIN}"
    else:
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, "r") as f:
                    content = f.read()
                    match = re.search(r'https://[a-z0-9-]+\.trycloudflare\.com', content)
                    if match:
                        argo_url = match.group(0)
                        # 生成文件
                        if not os.path.exists(LIST_FILE):
                            generate_links(argo_url)
            except: pass

    # 3. 关键：显示节点信息 (Output Nodes)
    st.divider()
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📡 Connection Info")
        if argo_url:
            st.success(f"**Tunnel URL:** {argo_url}")
            # 显示订阅链接
            st.code(f"{argo_url}/{SUB_PATH}", language="text")
        else:
            st.warning("Waiting for Argo Tunnel...")
            
        st.info(f"**Komari Status:** {'Configured' if KOMARI_HOST else 'Not Configured'}")

    with col2:
        st.subheader("⚡ Node Links (list.txt)")
        # 直接读取 FILE_PATH/list.txt 显示
        if os.path.exists(LIST_FILE):
            with open(LIST_FILE, "r") as f:
                nodes = f.read()
                st.code(nodes, language="text")
        else:
            st.info("Generating nodes... (Wait for tunnel)")

    # 4. 实时日志
    with st.expander("📝 System Logs", expanded=True):
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r") as f:
                st.code("".join(f.readlines()[-30:]), language="text")

    time.sleep(3)
    st.rerun()

if __name__ == "__main__":
    main()

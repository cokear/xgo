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

# ==========================================
# === 环境变量配置区域
# ==========================================
UPLOAD_URL = os.environ.get('UPLOAD_URL', '')            # 节点或订阅上传地址
PROJECT_URL = os.environ.get('PROJECT_URL', '')          # 项目url,用于保活
AUTO_ACCESS = os.environ.get('AUTO_ACCESS', 'false').lower() == 'true'  # 是否开启自动保活
FILE_PATH = os.environ.get('FILE_PATH', './.cache')      # 运行路径
SUB_PATH = os.environ.get('SUB_PATH', 'sub')             # 订阅路径
UUID = os.environ.get('UUID', '20e6e496-cf19-45c8-b883-14f5e11cd9f1')  # UUID
ARGO_DOMAIN = os.environ.get('ARGO_DOMAIN', '')          # Argo域名
ARGO_AUTH = os.environ.get('ARGO_AUTH', '')              # Argo Token/Secret
ARGO_PORT = int(os.environ.get('PORT', '8001'))
CFIP = os.environ.get('CFIP', 'cf.877774.xyz')           # 优选IP
CFPORT = int(os.environ.get('CFPORT', '443'))            # 优选端口
NAME = os.environ.get('NAME', 'Stream')                  # 节点名称
CHAT_ID = os.environ.get('CHAT_ID', '')                  # TG Chat ID
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')              # TG Bot Token

# --- 新增 Komari 变量 (替换原 Nezha 变量) ---
KOMARI_HOST = os.environ.get('KOMARI_HOST', '')          # Komari 面板地址 (不带http, 例如: status.example.com)
KOMARI_TOKEN = os.environ.get('KOMARI_TOKEN', '')        # Komari Agent Token

# ==========================================
# === 核心逻辑区域
# ==========================================

# 创建运行目录
def create_directory():
    print('\033c', end='')
    if not os.path.exists(FILE_PATH):
        os.makedirs(FILE_PATH)
        print(f"{FILE_PATH} is created")
    else:
        print(f"{FILE_PATH} already exists")

# 全局文件路径定义
komari_path = os.path.join(FILE_PATH, 'komari') # 替换 npm/php
web_path = os.path.join(FILE_PATH, 'web')
bot_path = os.path.join(FILE_PATH, 'bot')
sub_path = os.path.join(FILE_PATH, 'sub.txt')
list_path = os.path.join(FILE_PATH, 'list.txt')
boot_log_path = os.path.join(FILE_PATH, 'boot.log')
config_path = os.path.join(FILE_PATH, 'config.json')

# 删除旧节点 (保持原逻辑)
def delete_nodes():
    try:
        if not UPLOAD_URL: return
        if not os.path.exists(sub_path): return

        try:
            with open(sub_path, 'r') as file: file_content = file.read()
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

# 清理旧文件 (修改：增加清理 komari)
def cleanup_old_files():
    # 移除了 npm, php，加入了 komari
    paths_to_delete = ['web', 'bot', 'komari', 'npm', 'php', 'boot.log', 'list.txt', 'config.yaml']
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

# 获取系统架构
def get_system_architecture():
    architecture = platform.machine().lower()
    if 'arm' in architecture or 'aarch64' in architecture:
        return 'arm'
    else:
        return 'amd'

# 下载文件
def download_file(file_name, file_url):
    file_path = os.path.join(FILE_PATH, file_name)
    try:
        # 使用 ghfast 加速 github 链接，避免连接失败
        if "github.com" in file_url:
            file_url = f"https://ghfast.top/{file_url}"
            
        response = requests.get(file_url, stream=True, timeout=30)
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

# 根据架构获取文件列表 (修改：适配 Komari)
def get_files_for_architecture(architecture):
    # Komari 的发布文件名通常是 amd64 或 arm64
    k_arch = "arm64" if architecture == 'arm' else "amd64"
    
    # 保持原脚本的 web/bot 下载源 (ssss.nyc.mn)
    if architecture == 'arm':
        base_files = [
            {"fileName": "web", "fileUrl": "https://arm64.ssss.nyc.mn/web"},
            {"fileName": "bot", "fileUrl": "https://arm64.ssss.nyc.mn/2go"}
        ]
    else:
        base_files = [
            {"fileName": "web", "fileUrl": "https://amd64.ssss.nyc.mn/web"},
            {"fileName": "bot", "fileUrl": "https://amd64.ssss.nyc.mn/2go"}
        ]

    # 添加 Komari Agent 下载任务
    if KOMARI_HOST and KOMARI_TOKEN:
        komari_url = f"https://github.com/komari-monitor/komari-agent/releases/latest/download/komari-agent-linux-{k_arch}"
        base_files.insert(0, {"fileName": "komari", "fileUrl": komari_url})

    return base_files

# 赋予执行权限
def authorize_files(file_paths):
    for relative_file_path in file_paths:
        absolute_file_path = os.path.join(FILE_PATH, relative_file_path)
        if os.path.exists(absolute_file_path):
            try:
                os.chmod(absolute_file_path, 0o775)
                print(f"Empowerment success for {absolute_file_path}: 775")
            except Exception as e:
                print(f"Empowerment failed for {absolute_file_path}: {e}")

# 配置 Argo
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
        print("Use token connect to tunnel, please set the {ARGO_PORT} in cloudflare")

# 执行 Shell 命令
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

# 下载并运行核心服务
async def download_files_and_run():
    architecture = get_system_architecture()
    files_to_download = get_files_for_architecture(architecture)

    if not files_to_download:
        print("Can't find a file for the current architecture")
        return

    # 下载文件
    download_success = True
    for file_info in files_to_download:
        if not download_file(file_info["fileName"], file_info["fileUrl"]):
            download_success = False

    if not download_success:
        print("Error downloading files")
        return

    # 授权文件
    files_to_authorize = ['komari', 'web', 'bot'] if (KOMARI_HOST and KOMARI_TOKEN) else ['web', 'bot']
    authorize_files(files_to_authorize)

    # 生成 xray/singbox 配置 (web config)
    config ={"log":{"access":"/dev/null","error":"/dev/null","loglevel":"none",},"inbounds":[{"port":ARGO_PORT ,"protocol":"vless","settings":{"clients":[{"id":UUID ,"flow":"xtls-rprx-vision",},],"decryption":"none","fallbacks":[{"dest":3001 },{"path":"/vless-argo","dest":3002 },{"path":"/vmess-argo","dest":3003 },{"path":"/trojan-argo","dest":3004 },],},"streamSettings":{"network":"tcp",},},{"port":3001 ,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":UUID },],"decryption":"none"},"streamSettings":{"network":"ws","security":"none"}},{"port":3002 ,"listen":"127.0.0.1","protocol":"vless","settings":{"clients":[{"id":UUID ,"level":0 }],"decryption":"none"},"streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/vless-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},{"port":3003 ,"listen":"127.0.0.1","protocol":"vmess","settings":{"clients":[{"id":UUID ,"alterId":0 }]},"streamSettings":{"network":"ws","wsSettings":{"path":"/vmess-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},{"port":3004 ,"listen":"127.0.0.1","protocol":"trojan","settings":{"clients":[{"password":UUID },]},"streamSettings":{"network":"ws","security":"none","wsSettings":{"path":"/trojan-argo"}},"sniffing":{"enabled":True ,"destOverride":["http","tls","quic"],"metadataOnly":False }},],"outbounds":[{"protocol":"freedom","tag": "direct" },{"protocol":"blackhole","tag":"block"}]}
    with open(os.path.join(FILE_PATH, 'config.json'), 'w', encoding='utf-8') as config_file:
        json.dump(config, config_file, ensure_ascii=False, indent=2)

    # 运行 Komari (替换原 Nezha 运行逻辑)
    if KOMARI_HOST and KOMARI_TOKEN:
        # Komari 启动命令更加简洁
        komari_args = f"-e {KOMARI_HOST} -t {KOMARI_TOKEN} --disable-web-ssh --disable-auto-update"
        command = f"nohup {os.path.join(FILE_PATH, 'komari')} {komari_args} >/dev/null 2>&1 &"

        try:
            exec_cmd(command)
            print('komari is running')
            time.sleep(1)
        except Exception as e:
            print(f"komari running error: {e}")
    else:
        print('KOMARI variable is empty, skipping running')

    # 运行 web (节点核心)
    command = f"nohup {os.path.join(FILE_PATH, 'web')} -c {os.path.join(FILE_PATH, 'config.json')} >/dev/null 2>&1 &"
    try:
        exec_cmd(command)
        print('web is running')
        time.sleep(1)
    except Exception as e:
        print(f"web running error: {e}")

    # 运行 bot (Cloudflared)
    if os.path.exists(os.path.join(FILE_PATH, 'bot')):
        if re.match(r'^[A-Z0-9a-z=]{120,250}$', ARGO_AUTH):
            args = f"tunnel --edge-ip-version auto --no-autoupdate --protocol http2 run --token {ARGO_AUTH}"
        elif "TunnelSecret" in ARGO_AUTH:
            args = f"tunnel --edge-ip-version auto --config {os.path.join(FILE_PATH, 'tunnel.yml')} run"
        else:
            args = f"tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {os.path.join(FILE_PATH, 'boot.log')} --loglevel info --url http://localhost:{ARGO_PORT}"

        try:
            exec_cmd(f"nohup {os.path.join(FILE_PATH, 'bot')} {args} >/dev/null 2>&1 &")
            print('bot is running')
            time.sleep(2)
        except Exception as e:
            print(f"Error executing command: {e}")

    time.sleep(5)
    await extract_domains()

# 提取域名逻辑 (保持不变)
async def extract_domains():
    argo_domain = None

    if ARGO_AUTH and ARGO_DOMAIN:
        argo_domain = ARGO_DOMAIN
        print(f'ARGO_DOMAIN: {argo_domain}')
        await generate_links(argo_domain)
    else:
        try:
            with open(boot_log_path, 'r') as f: file_content = f.read()
            lines = file_content.split('\n')
            argo_domains = []
            for line in lines:
                domain_match = re.search(r'https?://([^ ]*trycloudflare\.com)/?', line)
                if domain_match:
                    domain = domain_match.group(1)
                    argo_domains.append(domain)

            if argo_domains:
                argo_domain = argo_domains[0]
                print(f'ArgoDomain: {argo_domain}')
                await generate_links(argo_domain)
            else:
                print('ArgoDomain not found, re-running bot...')
                if os.path.exists(boot_log_path): os.remove(boot_log_path)
                try: exec_cmd('pkill -f "[b]ot" > /dev/null 2>&1')
                except: pass
                time.sleep(1)
                args = f'tunnel --edge-ip-version auto --no-autoupdate --protocol http2 --logfile {FILE_PATH}/boot.log --loglevel info --url http://localhost:{ARGO_PORT}'
                exec_cmd(f'nohup {os.path.join(FILE_PATH, "bot")} {args} >/dev/null 2>&1 &')
                time.sleep(6)
                await extract_domains()
        except Exception as e:
            print(f'Error reading boot.log: {e}')

# 上传节点 (保持不变)
def upload_nodes():
    if UPLOAD_URL and PROJECT_URL:
        subscription_url = f"{PROJECT_URL}/{SUB_PATH}"
        json_data = {"subscription": [subscription_url]}
        try:
            requests.post(f"{UPLOAD_URL}/api/add-subscriptions", json=json_data, headers={"Content-Type": "application/json"})
            print('Subscription uploaded successfully')
        except: pass

    elif UPLOAD_URL:
        if not os.path.exists(list_path): return
        with open(list_path, 'r') as f: content = f.read()
        nodes = [line for line in content.split('\n') if any(protocol in line for protocol in ['vless://', 'vmess://', 'trojan://', 'hysteria2://', 'tuic://'])]
        if not nodes: return
        try:
            requests.post(f"{UPLOAD_URL}/api/add-nodes", data=json.dumps({"nodes": nodes}), headers={"Content-Type": "application/json"})
            print('Nodes uploaded successfully')
        except: return None

# TG 推送 (保持不变)
def send_telegram():
    if not BOT_TOKEN or not CHAT_ID: return
    try:
        with open(sub_path, 'r') as f: message = f.read()
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        escaped_name = re.sub(r'([_*\[\]()~>#+=|{}.!\-])', r'\\\1', NAME)
        params = {"chat_id": CHAT_ID, "text": f"**{escaped_name}节点推送通知**\n{message}", "parse_mode": "MarkdownV2"}
        requests.post(url, params=params)
        print('Telegram message sent successfully')
    except Exception as e:
        print(f'Failed to send Telegram message: {e}')

# 生成链接 (保持不变)
async def generate_links(argo_domain):
    meta_info = subprocess.run(['curl', '-s', 'https://speed.cloudflare.com/meta'], capture_output=True, text=True)
    try:
        meta_info = meta_info.stdout.split('"')
        ISP = f"{meta_info[25]}-{meta_info[17]}".replace(' ', '_').strip()
    except: ISP = "Cloudflare"

    time.sleep(2)
    VMESS = {"v": "2", "ps": f"{NAME}-{ISP}", "add": CFIP, "port": CFPORT, "id": UUID, "aid": "0", "scy": "none", "net": "ws", "type": "none", "host": argo_domain, "path": "/vmess-argo?ed=2560", "tls": "tls", "sni": argo_domain, "alpn": "", "fp": "chrome"}

    list_txt = f"""
vless://{UUID}@{CFIP}:{CFPORT}?encryption=none&security=tls&sni={argo_domain}&fp=chrome&type=ws&host={argo_domain}&path=%2Fvless-argo%3Fed%3D2560#{NAME}-{ISP}

vmess://{ base64.b64encode(json.dumps(VMESS).encode('utf-8')).decode('utf-8')}

trojan://{UUID}@{CFIP}:{CFPORT}?security=tls&sni={argo_domain}&fp=chrome&type=ws&host={argo_domain}&path=%2Ftrojan-argo%3Fed%3D2560#{NAME}-{ISP}
    """

    with open(os.path.join(FILE_PATH, 'list.txt'), 'w', encoding='utf-8') as list_file: list_file.write(list_txt)
    sub_txt = base64.b64encode(list_txt.encode('utf-8')).decode('utf-8')
    with open(os.path.join(FILE_PATH, 'sub.txt'), 'w', encoding='utf-8') as sub_file: sub_file.write(sub_txt)

    print(sub_txt)
    print(f"{FILE_PATH}/sub.txt saved successfully")
    send_telegram()
    upload_nodes()
    return sub_txt

# 外部保活任务 (保持不变)
def add_visit_task():
    if not AUTO_ACCESS or not PROJECT_URL:
        print("Skipping adding automatic access task")
        return
    try:
        requests.post('https://keep.gvrander.eu.org/add-url', json={"url": PROJECT_URL}, headers={"Content-Type": "application/json"})
        print('automatic access task added successfully')
    except Exception as e:
        print(f'Failed to add URL: {e}')

# 清理文件 (仅清理非必要文件，保留进程)
def clean_files():
    def _cleanup():
        time.sleep(90)
        # 移除了 komari, web, bot 的清理，只清理配置和日志
        # 如果你希望运行完删除所有文件但保留内存进程，可以把 web, bot, komari 加回去
        # 原脚本是删除了所有的。这里我还原原脚本逻辑：
        files_to_delete = [boot_log_path, config_path, list_path, web_path, bot_path, komari_path]
        for file in files_to_delete:
            try:
                if os.path.exists(file):
                    if os.path.isdir(file): shutil.rmtree(file)
                    else: os.remove(file)
            except: pass
        print('\033c', end='')
        print('App is running')
        print('Thank you for using this script, enjoy!')

    threading.Thread(target=_cleanup, daemon=True).start()

# 主函数
async def start_server():
    delete_nodes()
    cleanup_old_files()
    create_directory()
    argo_type()
    await download_files_and_run()
    add_visit_task()
    clean_files()
    print("Running done!")
    print(f"\nLogs will be deleted in 90 seconds")

# 异步入口 + 死循环保活 (保持原逻辑)
def run_async():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_server())

    # === 关键的进程保活逻辑 ===
    # 保持主线程不退出，从而守护后台进程 (komari, web, bot)
    while True:
        time.sleep(3600)

if __name__ == "__main__":
    run_async()

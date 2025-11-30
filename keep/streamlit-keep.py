import os
import time
import logging
import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class StreamlitAppWaker:
    APP_URL = os.environ.get("STREAMLIT_APP_URL", "")
    INITIAL_WAIT_TIME = 15
    POST_CLICK_WAIT_TIME = 20
    
    # 1. 休眠关键词 (需要点击唤醒)
    SLEEP_KEYWORDS = [
        "Yes, get this app back up",
        "Your app has gone to sleep",
        "Wake up"
    ]
    
    # 2. 崩溃关键词 (需要人工介入或重启) - 新增检测！
    CRASH_KEYWORDS = [
        "Oh no",
        "Error running app",
        "contact support",
        "Streamlit server is currently unavailable"
    ]
    
    # 按钮定位
    BUTTON_SELECTOR = f"//button[contains(., 'Yes, get this app back up') or contains(., 'Wake up')]"
    
    def __init__(self):
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        logger.info("⚙️ 正在设置Chrome驱动...")
        chrome_options = Options()
        
        if os.getenv('GITHUB_ACTIONS'):
            logger.info("⚙️ 检测到CI环境，启用headless模式。")
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')

        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("✅ Chrome驱动设置完成。")
        except Exception as e:
            logger.error(f"❌ 驱动初始化失败: {e}")
            raise

    def save_debug_artifacts(self, suffix="error"):
        if not self.driver: return
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            self.driver.save_screenshot(f"debug_{suffix}_{timestamp}.png")
            with open(f"debug_{suffix}_{timestamp}.html", "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.info(f"📸 [DEBUG] 已保存截图和源码: debug_{suffix}_{timestamp}")
        except Exception:
            pass

    def check_text_in_context(self, context_name):
        """检查当前上下文的文本，返回 (状态码, 关键词)"""
        # 状态码: 0=正常, 1=休眠, 2=崩溃
        try:
            body = self.driver.find_element(By.TAG_NAME, "body")
            text = body.text
            if not text.strip():
                text = self.driver.execute_script("return document.body.innerText || document.body.textContent;")
            
            # 优先检查崩溃
            for keyword in self.CRASH_KEYWORDS:
                if keyword in text:
                    logger.error(f"🚨 [{context_name}] 发现崩溃关键词: '{keyword}'")
                    return 2, keyword
            
            # 检查休眠
            for keyword in self.SLEEP_KEYWORDS:
                if keyword in text:
                    logger.info(f"💤 [{context_name}] 发现休眠关键词: '{keyword}'")
                    return 1, keyword
                    
            return 0, None
        except Exception:
            return 0, None

    def scan_page_status(self):
        """扫描主页面和所有iframe的状态"""
        # 1. 检查主页面
        self.driver.switch_to.default_content()
        status, keyword = self.check_text_in_context("Main")
        if status != 0: return status, keyword, None

        # 2. 检查 iframe
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            for i, iframe in enumerate(iframes):
                self.driver.switch_to.default_content()
                self.driver.switch_to.frame(iframe)
                status, keyword = self.check_text_in_context(f"Iframe-{i}")
                if status != 0: 
                    self.driver.switch_to.default_content()
                    return status, keyword, i
                self.driver.switch_to.default_content()
        except Exception:
            pass
            
        return 0, None, None

    def find_and_click_wakeup(self, iframe_index=None):
        """尝试点击唤醒按钮"""
        # 如果在 iframe 里，先切进去
        if iframe_index is not None:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if len(iframes) > iframe_index:
                self.driver.switch_to.frame(iframes[iframe_index])
        
        # 1. 常规点击
        try:
            btn = WebDriverWait(self.driver, 3).until(EC.element_to_be_clickable((By.XPATH, self.BUTTON_SELECTOR)))
            self.driver.execute_script("arguments[0].click();", btn)
            return True
        except:
            pass
            
        # 2. Shadow DOM 点击
        js = """
        function scan(root) {
            if(root.querySelectorAll) {
                root.querySelectorAll('button').forEach(b => {
                    if(b.innerText.includes('Yes, get this app') || b.innerText.includes('Wake up')) b.click();
                });
                root.querySelectorAll('*').forEach(e => { if(e.shadowRoot) scan(e.shadowRoot); });
            }
        }
        scan(document);
        """
        try:
            self.driver.execute_script(js)
            # 简单假设执行没报错就算尝试过了，具体是否成功靠后验
            time.sleep(2)
            return True
        except:
            return False

    def run_check(self):
        if not self.APP_URL: raise Exception("⚠️ 未配置 STREAMLIT_APP_URL")
        
        logger.info(f"👉 访问: {self.APP_URL}")
        self.driver.get(self.APP_URL)
        time.sleep(self.INITIAL_WAIT_TIME)
        
        # 第一次扫描
        status, keyword, iframe_idx = self.scan_page_status()
        
        if status == 2:
            # 状态 2: 崩溃
            self.save_debug_artifacts("crash_detected")
            return False, f"❌ 应用已崩溃！页面包含: '{keyword}'。请手动登录并重启应用。"
            
        elif status == 1:
            # 状态 1: 休眠
            logger.info(f"💤 检测到休眠 (关键词: {keyword})，尝试唤醒...")
            self.find_and_click_wakeup(iframe_idx)
            
            logger.info(f"⏳ 等待启动 {self.POST_CLICK_WAIT_TIME} 秒...")
            time.sleep(self.POST_CLICK_WAIT_TIME)
            
            # 复查
            status, _, _ = self.scan_page_status()
            if status == 0:
                return True, "✅ 唤醒成功！应用已恢复运行。"
            else:
                self.save_debug_artifacts("wakeup_failed")
                return False, "❌ 尝试唤醒失败，按钮点击后应用仍未恢复。"
                
        else:
            # 状态 0: 正常 (或未知错误)
            # 为了保险，这里我们可以认为它是正常的，但在 logs 里记录
            return True, "✅ 应用处于运行状态 (未检测到休眠或崩溃信息)。"

    def run(self):
        try:
            logger.info("🚀 开始检测...")
            success, result = self.run_check() 
            return success, result
        except Exception as e:
            logger.error(f"❌ 脚本错误: {e}")
            if self.driver: self.save_debug_artifacts("script_error")
            return False, str(e)
        finally:
            if self.driver: self.driver.quit()

def main():
    waker = StreamlitAppWaker()
    success, result = waker.run()
    logger.info(f"🏁 结果: {result}")
    
    # 关键修改：如果检测到崩溃 (success=False)，这里会退出代码 1
    # 这会让 GitHub Actions 标记为红色失败，你会收到通知
    exit(0 if success else 1)

if __name__ == "__main__":
    main()

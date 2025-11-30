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
    """
    针对Streamlit应用的自动唤醒脚本 (调试增强版)
    """
    
    APP_URL = os.environ.get("STREAMLIT_APP_URL", "https://idralguxkuj6pvd8sukcww.streamlit.app/")
    INITIAL_WAIT_TIME = 15  # 增加初始等待时间，防止加载过慢
    POST_CLICK_WAIT_TIME = 20
    # 使用 contains(., ...) 可以匹配子元素文本，比 contains(text(), ...) 更稳健
    BUTTON_SELECTOR = "//button[contains(., 'Yes, get this app back up')]"
    
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
        else:
            # 本地调试时，如果不想看浏览器弹窗，可以取消下面注释
            # chrome_options.add_argument('--headless') 
            pass

        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--ignore-certificate-errors')
        # 允许不安全的内容，防止某些资源加载失败
        chrome_options.add_argument('--allow-running-insecure-content')
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            logger.info("✅ Chrome驱动设置完成。")
        except Exception as e:
            logger.error(f"❌ 驱动初始化失败: {e}")
            raise

    def save_debug_artifacts(self, suffix="error"):
        """保存截图和HTML源码用于调试"""
        if not self.driver:
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_name = f"debug_{suffix}_{timestamp}.png"
        html_name = f"debug_{suffix}_{timestamp}.html"
        
        try:
            self.driver.save_screenshot(screenshot_name)
            logger.info(f"📸 [DEBUG] 已保存截图: {screenshot_name}")
        except Exception as e:
            logger.warning(f"⚠️ 无法保存截图: {e}")

        try:
            with open(html_name, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            logger.info(f"📄 [DEBUG] 已保存页面源码: {html_name}")
        except Exception as e:
            logger.warning(f"⚠️ 无法保存页面源码: {e}")

    def log_visible_buttons(self):
        """[调试用] 打印当前页面所有可见按钮的文本"""
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            visible_texts = [b.text.strip() for b in buttons if b.is_displayed() and b.text.strip()]
            if visible_texts:
                logger.info(f"🧐 [DEBUG] 当前页面发现的可见按钮: {visible_texts}")
            else:
                logger.info("🧐 [DEBUG] 当前页面没有找到可见的 <button> 标签。")
        except Exception:
            pass

    def wait_for_element_clickable(self, by, value, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )
    
    def find_and_click_button(self, context_description="主页面"):
        logger.info(f"🔍 尝试在 {context_description} 查找唤醒按钮...")
        
        try:
            # 缩短这里的超时，因为我们会重试或者切iframe
            button = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, self.BUTTON_SELECTOR))
            )
            
            if button.is_displayed() and button.is_enabled():
                # 尝试滚动到元素位置，防止被遮挡
                self.driver.execute_script("arguments[0].scrollIntoView(true);", button)
                time.sleep(1) 
                button.click()
                logger.info(f"✅ 在 {context_description} 成功点击唤醒按钮。")
                return True
            else:
                logger.warning(f"⚠️ 在 {context_description} 找到按钮，但不可交互。")
                return False

        except TimeoutException:
            logger.info(f"❌ 在 {context_description} 未找到唤醒按钮。")
            return False
        except Exception as e:
            logger.error(f"❌ 在 {context_description} 点击按钮异常: {e}")
            return False

    def is_app_woken_up(self):
        logger.info("🧐 检查唤醒按钮是否已消失...")
        self.driver.switch_to.default_content()
        try:
            WebDriverWait(self.driver, 5).until(
                EC.presence_of_element_located((By.XPATH, self.BUTTON_SELECTOR))
            )
            logger.info("❌ 唤醒按钮仍在主页面显示。")
            return False
        except TimeoutException:
            # 主页面没有，检查iframe
            pass
            
        try:
            iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
            if not iframes:
                return True

            for iframe in iframes:
                self.driver.switch_to.frame(iframe)
                try:
                    WebDriverWait(self.driver, 1).until(
                        EC.presence_of_element_located((By.XPATH, self.BUTTON_SELECTOR))
                    )
                    self.driver.switch_to.default_content()
                    logger.info("❌ 唤醒按钮在 iframe 内仍显示。")
                    return False
                except TimeoutException:
                    self.driver.switch_to.default_content()
            
            logger.info("✅ 应用唤醒成功，按钮已消失。")
            return True

        except Exception as e:
            self.driver.switch_to.default_content()
            logger.error(f"❌ 检查状态异常: {e}")
            return False

    def wakeup_app(self):
        if not self.APP_URL:
            raise Exception("⚠️ 环境变量 STREAMLIT_APP_URL 未配置。")
            
        logger.info(f"👉 访问: {self.APP_URL}")
        self.driver.get(self.APP_URL)
        
        # 打印调试信息
        logger.info(f"📄 Page Title: {self.driver.title}")
        logger.info(f"🔗 Current URL: {self.driver.current_url}")
        
        logger.info(f"⏳ 等待加载 {self.INITIAL_WAIT_TIME} 秒...")
        time.sleep(self.INITIAL_WAIT_TIME)
        
        # 调试：打印所有可见按钮，看看是否有文案变动
        self.log_visible_buttons()
        
        click_success = self.find_and_click_button("主页面")
        
        if not click_success:
            logger.info("👉 尝试进入 iframe 查找...")
            try:
                iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
                logger.info(f"🔢 发现 {len(iframes)} 个 iframe")
                
                for i, iframe in enumerate(iframes):
                    try:
                        self.driver.switch_to.frame(iframe)
                        # 在iframe里也打印一下按钮
                        self.log_visible_buttons()
                        
                        if self.find_and_click_button(f"iframe[{i+1}]"):
                            click_success = True
                            break
                    except Exception as e:
                         logger.warning(f"处理 iframe[{i}] 出错: {e}")
                    finally:
                        self.driver.switch_to.default_content()
            except Exception as e:
                logger.error(f"❌ iframe 处理全流程出错: {e}")
                
        if not click_success:
            # 保存失败现场
            self.save_debug_artifacts("not_found")
            
            if self.is_app_woken_up():
                return True, "✅ 应用似乎已是唤醒状态。" 
            else:
                return False, "⚠️ 找不到按钮。请查看生成的 debug_not_found_*.png 截图排查原因。"
        
        logger.info(f"⏳ 等待应用启动 {self.POST_CLICK_WAIT_TIME} 秒...")
        time.sleep(self.POST_CLICK_WAIT_TIME)
        
        if self.is_app_woken_up():
            return True, "✅ 唤醒成功！"
        else:
            self.save_debug_artifacts("still_sleeping")
            return False, "❌ 点击后按钮未消失，可能唤醒失败。请查看 debug_still_sleeping_*.png。"

    def run(self):
        try:
            logger.info("🚀 开始执行...")
            success, result = self.wakeup_app() 
            return success, result
        except Exception as e:
            logger.error(f"❌ 严重错误: {e}")
            if self.driver:
                self.save_debug_artifacts("crash")
            return False, str(e)
        finally:
            if self.driver:
                logger.info("🧹 关闭驱动...")
                self.driver.quit()

def main():
    app_url = os.environ.get("STREAMLIT_APP_URL", "")
    if not app_url:
        logger.warning("⚠️ 未配置 STREAMLIT_APP_URL，请设置环境变量。")
    
    waker = StreamlitAppWaker()
    success, result = waker.run()
    logger.info(f"🏁 结果: {result}")
    
    if success:
        exit(0)
    else:
        exit(1)

if __name__ == "__main__":
    main()

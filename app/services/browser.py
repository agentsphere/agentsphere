from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException
from selenium_stealth import stealth
from webdriver_manager.chrome import ChromeDriverManager

from app.config import logger

def create_stealth_driver():
    """
    Initializes a Chrome WebDriver with stealth configurations to reduce detection.

    Returns:
        webdriver.Chrome: A configured instance of Chrome WebDriver.
    """
    chrome_options = Options()

    # Browser window and behavior
    chrome_options.add_argument("--start-maximized")

    # Uncomment for headless mode if needed (new mode is better for stealth)
    chrome_options.add_argument("--headless=new")

    # Custom user-agent to mimic a real browser
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")

    # Disable automation-related flags to avoid detection
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-notifications")

    # Initialize Chrome WebDriver
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    # Apply stealth techniques
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc. (Apple)",
        platform="MacIntel",
        webgl_vendor="Google Inc. (Apple)",
        renderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Max, Unspecified Version)",
        fix_hairline=True,
    )

    return driver


def get_page_with_selenium(url: str) -> str:
    """getPageWithSelenium
    Fetches the HTML content of a page using a stealth-enabled Selenium driver.

    Args:
        url (str): The target webpage URL.

    Returns:
        str: HTML content of the loaded page.
    """
    driver = create_stealth_driver()

    try:
        driver.get(url)
        WebDriverWait(driver, 3).until(
            lambda d: d.execute_script(
                """
                return window.performance.getEntriesByType('resource')
                .filter(e => ['xmlhttprequest', 'fetch', 'script', 'css', 'iframe', 'beacon', 'other'].includes(e.initiatorType)).length === 0;
                """
            )
        )
        page_source = driver.page_source
        logger.info("Could load page %s, not None", url)
    except TimeoutException as e:
        print("Timeout waiting for network requests:", e)
        page_source = driver.page_source
        logger.info("Getting page even if not fully loaded %s", url)
        logger.info("Page source {len(page_source)}")
        return page_source
    finally:
        driver.quit()
    return None

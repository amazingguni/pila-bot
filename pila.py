import time
import os 

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException

from pytz import timezone
from datetime import datetime, timedelta
from slacker import Slacker
from threading import Thread

TIMEOUT = 20
LONG_TIMEOUT = 30

# 화요일에는 수목가 열리고, 목요일에는 금토이 열리고, 일요일에는 월화
OPENING_HOUR = 12
OPENING_MINUTE = 0


KST = timezone('Asia/Seoul')

def get_index_of_weekday(weekday_str):
    WEEKDAY_STRS = '월화수목금토일'
    return WEEKDAY_STRS.index(weekday_str)

def init_browser():
    options = Options()
    # If CircleCI
    if os.environ.get('CI'):
        options.headless = True
        browser = webdriver.Chrome(executable_path="chromedriver", options=options)
    else:
        browser = webdriver.Chrome(executable_path="./driver/mac/chromedriver", options=options)
    browser.get("http://aprilpilates2.flexgym.pro/mobile2/")
    element = WebDriverWait(browser, LONG_TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, 'banner99_chk')))
    element.click()
    element = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, 'pop_close')))
    element.click()
    return browser

def login(browser, user, password):
    element = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.ID, "memberID")))
    element.send_keys(user)
    element = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.ID, "memberPW")))
    element.send_keys(password)
    element.send_keys(Keys.RETURN)
    elements = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '#paymentList li')))
    elements[0].click()

def get_display_date(browser):
    element = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.CLASS_NAME, 'btnShowWeek')))
    return element.text

def is_reserved_before(reservelist_element):
    return '(예약완료)' in reservelist_element.text

def is_openned(reservelist_element):
    return '관련내용이 존재하지 않습니다' not in reservelist_element.text
        
def reserve_date_class(browser, target_datetime):
    target_date_str = target_datetime.strftime("%Y-%m-%d")
    target_time_str = target_datetime.strftime("%H:%M")
    target_weekday = target_datetime.strftime("%A")
    print(f'Try to reserve {target_date_str} {target_weekday}')
    TOTAL_RETRY_CNT = 30
    for i in range(TOTAL_RETRY_CNT):
        browser.execute_script(f"funcSearch01('{target_date_str}','C')")
        reservelist_element = WebDriverWait(browser, TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, '#reserveList')))
        if is_reserved_before(reservelist_element):
            print(f'You have a reservation for this day.({target_date_str})')
            return []
        if is_openned(reservelist_element):
            print(f'There are a lot of classes you can reserve. target date is openned!!!')
            break
        print(f'There are no classes yet({target_date_str})')
        time.sleep(0.5)
        
    li_elements = reservelist_element.find_elements_by_css_selector('li:not(.nothing)')
    for li in li_elements:
        try:
            class_name = li.find_element_by_css_selector('.mName div').text
            class_time = li.find_element_by_css_selector('.rTime div').text
            class_num = li.find_element_by_css_selector('.rNum div').text
            if target_time_str not in class_time:
                continue
            if '(정원초과)' in class_num:
                print(f'Can not reserve {class_name} {class_time}(정원초과)')
                break
            # 정원초과나 예약 가능일 때 (정원초과), (예약가능)이 뜨지 않는 문제가 있어서
            # 그냥 숫자로 판단하는 것으로 변경, 상태에 따라 버튼의 class도 변경되지 않는 것으로 보임
            print(f'booked_num_text: {class_num}')
            booked_num_text = class_num.replace('(예약가능)', '').replace(' ', '')
            current_cnt, limit = [int(each) for each in booked_num_text.split('/')]
            if current_cnt >= limit:
                print(f'Can not reserve {class_name} {class_time}(정원초과)')
                break
            # 리스트에서 상세 보기 버튼 클릭
            # complete1: 예약 불가능(내 예약 존재)
            # complete4: 예약 불가능(내 예약 없음)
            # complete5: 예약 가능(내 예약 없음)
            # 광고가 클릭되는 경우가 많아서 onclick을 받아서 실행시키는 것으로 구현 변경
            button_element = li.find_element_by_css_selector('.rbutton button')
            button_onclick_text = button_element.get_attribute('onclick')
            browser.execute_script(button_onclick_text)
            # button_element.click()
            # 상세 보기 팝업에서 예약 버튼 클릭
            reserve_button_element = WebDriverWait(browser, TIMEOUT).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, '.AVBtn')))
            reserve_button_onclick = reserve_button_element.get_attribute('onclick')
            browser.execute_script(reserve_button_onclick)
            # reserve_button_element.click()

            # 수강 신청 완료 확인 버튼 클릭
            WebDriverWait(browser, TIMEOUT).until(EC.alert_is_present())
            alert = browser.switch_to_alert()
            alert_text = alert.text
            alert.accept()
            if '수강예약이 완료되었습니다' in alert_text:
                print(f'필라테스 예약이 완료되었습니다. {class_name} {class_time}')
                return [(class_name, class_time)] 
        except NoSuchElementException as e:
            print(f'[error] {str(e)}')
    return []

def wait_for_openning_time(hour=OPENING_HOUR, minute=OPENING_MINUTE):
    target_time = datetime.now().astimezone(KST)
    target_time = target_time.replace(hour=hour, minute=minute, second=0)
    print(f'wait_for : {target_time.strftime("%Y-%m-%d %H:%M:%S")}')
    while True:
        now = datetime.now().astimezone(KST)
        print(f'wait_for : {target_time.strftime("%Y-%m-%d %H:%M:%S")} now: {now.strftime("%Y-%m-%d %H:%M:%S")}')
        remain_seconds = (target_time - now).total_seconds()
        # 10초 전까지 슬립
        if remain_seconds < 10: break
        time.sleep(remain_seconds / 2)


def send_slack_message(token, channel, title, message='', color="good"):
    if not slack_token:
        return
    slack = Slacker(slack_token)
    attachment = {
        "color": color,
        "title": title
    }

    if message:
        attachment['text'] = message
    if 'CIRCLE_BUILD_URL' in os.environ:
        attachment['title_link'] = os.environ['CIRCLE_BUILD_URL']
    slack.chat.post_message(channel, attachments=[attachment], as_user=True)

class BookingThread(Thread):
    def __init__(self, user, password, target_datetimes, wait_opening):
        super(BookingThread, self).__init__()
        self.user = user
        self.password = password
        self.target_datetimes = target_datetimes
        self.wait_opening = wait_opening
        self.reserved_classes = []

    def run(self):
        try:
            browser = init_browser()
            print('Start crawling')
            print(f'Login {self.user}')
            login(browser, self.user, self.password)
            display_date = get_display_date(browser)
            print(f'Today: {display_date}')
            if self.wait_opening:
                print('Wait opening time')
                wait_for_openning_time()
            
            for target_datetime in self.target_datetimes:
                self.reserved_classes += reserve_date_class(browser, target_datetime)
        finally:
            pass

def get_target_datetimes(time_str):
    now = datetime.now().astimezone(KST)
    ret = []
    for each in time_str.split(','):
        each = each.strip()
        weekday_idx = get_index_of_weekday(each[0])
        hour, minute = each[1:].split(':')
        hour = int(hour)
        minute = int(minute)
        diff_day = (weekday_idx - now.weekday() ) % 7
        if diff_day > 2: continue
        target = now + timedelta(days=(weekday_idx - now.weekday() ) % 7)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        ret.append(target)
    return ret


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', '-u', required=True, help='Username of pilates homepage')
    parser.add_argument('--password', '-p', required=True, help='Password of pilates homepage')
    parser.add_argument('--time', '-t', required=True, help='The time of the class you want to book(e.g, 20:00)')
    parser.add_argument('--slack-token', '-s', required=False, help='Slack token')
    parser.add_argument('--slack-channel', '-c', required=False, help='Slack channel')
    parser.add_argument('--worker-cnt', '-w', required=False, type=int, default=1, help='Worker count')
    parser.add_argument('--wait-opening', action='store_true', help='True if you want to wait for opening time')
    args = parser.parse_args()

    user = args.user
    password = args.password
    target_datetimes = get_target_datetimes(args.time)
    slack_token = args.slack_token
    slack_channel = args.slack_channel
    wait_opening = args.wait_opening
    worker_cnt = args.worker_cnt
    now = datetime.now().astimezone(KST)
    
    print(f'Now: {now.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Book pilates class at {args.time} now.({user})')
    if not target_datetimes:
        print(f'There is not date to reservation.({args.time})')
        exit(1)
    print(f'Target Datetime')
    for target in target_datetimes:
        print(f'  - {target.strftime("%Y-%m-%d %H:%M %A")}')
    print(f'Use {worker_cnt} workers')
    
    threads = []
    for i in range(worker_cnt):
        t = BookingThread(user, password, target_datetimes, wait_opening)
        threads.append(t)
        t.start()
    reserved_classes = []
    for t in threads:
        t.join()
        reserved_classes += t.reserved_classes
        
    if reserved_classes:
        print()
        for each in reserved_classes:
            print(f' - {each}')
        title = f'[{user}] Successfully book pilates classes :dancer:'
        message = '\n'.join([f'- `{each[1]}`({each[0]})' for each in reserved_classes])
        print(title + '\n' + message)
        send_slack_message(slack_token, slack_channel, title, message)
    else:
        title = f'[{user}] Couldn\'t book pilates classes :sob:'
        print(title)
        send_slack_message(slack_token, slack_channel, title, color='danger')

    
        
    

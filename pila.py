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

TIMEOUT = 20
LONG_TIMEOUT = 30

OPENING_HOUR = 12
OPENING_MINUTE = 0
# OPENING_HOUR = 21
# OPENING_MINUTE = 57

# 화요일에는 수목가 열리고, 목요일에는 금토이 열리고, 일요일에는 월화
KST = timezone('Asia/Seoul')

def get_indexes_of_target_weekday_indexes(target_weekday_str):
    WEEKDAY_STRS = '월화수목금토일'
    weekday_indexes = []
    for each in target_weekday_str:
        if each not in WEEKDAY_STRS:
            print(f'[ignored] {each} is not weekday string')
        weekday_indexes.append(WEEKDAY_STRS.index(each))
    return weekday_indexes

def get_target_dates(target_weekday_indexes):
    now = datetime.now().astimezone(KST)
    # today_weekday = now.weekday()
    # open_weekday = [1, 3, 6]
    # if today_weekday not in open_weekday:
    #     return []
    target_dates = [now + timedelta(days=1), now + timedelta(days=2)]
    return list(filter(lambda x: x.weekday() in target_weekday_indexes, target_dates))

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
    element = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.ID, 'datepickerC')))
    return element.get_attribute("value")

def is_reserved_before(reservelist_element):
    return '(예약완료)' in reservelist_element.text

def is_openned(reservelist_element):
    return '관련내용이 존재하지 않습니다' not in reservelist_element.text
        
def reserve_date_class(browser, target_date, target_time):
    target_date_str = target_date.strftime("%Y-%m-%d")
    print(f'Try to reserve {target_date_str} {target_date.strftime("%A")}')
    TOTAL_RETRY_CNT = 30
    for i in range(TOTAL_RETRY_CNT):
        browser.execute_script(f"funcSearch01('{target_date_str}','C')")
        reservelist_element = WebDriverWait(browser, TIMEOUT).until(EC.presence_of_element_located((By.CSS_SELECTOR, '#reserveList')))
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
            if target_time not in class_time:
                continue
            if '(정원초과)' in class_num:
                print(f'Can not reserve {class_name} {class_time}(정원초과)')
                break
            
            # 리스트에서 상세 보기 버튼 클릭
            # complete1: 예약 불가능(내 예약 존재)
            # complete4: 예약 불가능(내 예약 없음)
            # complete5: 예약 가능(내 예약 없음)
            button_element = li.find_element_by_css_selector('.rbutton .complete5')
            button_element.click()
            # 상세 보기 팝업에서 예약 버튼 클릭
            reserve_button_element = WebDriverWait(browser, TIMEOUT).until(EC.element_to_be_clickable((By.CSS_SELECTOR, '.AVBtn')))
            reserve_button_element.click()

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

def main(user, password, weekdays, target_time, wait_opening, slack_token, slack_channel):
    try:
        browser = init_browser()
        print('Start crawling')
        print(f'Login {user}')
        login(browser, user, password)
        display_date = get_display_date(browser)
        print(f'Today: {display_date}')
        target_weekday_indexes = get_indexes_of_target_weekday_indexes(weekdays)
        target_dates = get_target_dates(target_weekday_indexes)
        if not target_dates:
            print(f'There is not date to reservation.({weekdays})')
            return
        target_dates_str = ''.join([d.strftime("%Y-%m-%d %H:%M:%S") for d in target_dates])
        print(f'target_dates: {target_dates_str}')
        if wait_opening:
            print('Wait opening time')
            wait_for_openning_time()
        reserved_classes = []
        for date in target_dates:
            reserved_classes += reserve_date_class(browser, date, target_time)
        if reserved_classes:
            print()
            print(f'[Reserved classes]')
            for each in reserved_classes:
                print(f' - {each}')
        else:
            print('Couldn\'t book pilates classes')
    finally:
        pass

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--user', '-u', required=True, help='Username of pilates homepage')
    parser.add_argument('--password', '-p', required=True, help='Password of pilates homepage')
    parser.add_argument('--weekdays', '-w', required=True, help='Day of the class you want to book(e.g, 월수금)')
    parser.add_argument('--time', '-t', required=True, help='The time of the class you want to book(e.g, 20:00)')
    parser.add_argument('--slack-token', '-s', required=False, help='Slack token')
    parser.add_argument('--slack-channel', '-c', required=False, help='Slack channel')
    parser.add_argument('--wait-opening', action='store_true', help='True if you want to wait for opening time')
    args = parser.parse_args()

    user = args.user
    password = args.password
    weekdays = args.weekdays
    target_time = args.time
    slack_token = args.slack_token
    slack_channel = args.slack_channel
    wait_opening = args.wait_opening
    now = datetime.now().astimezone(KST)
    print(f'Now: {now.strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Book pilates class at {target_time} on {weekdays} now.({user})')
    main(user, password, weekdays, target_time, wait_opening, slack_token, slack_channel)
    
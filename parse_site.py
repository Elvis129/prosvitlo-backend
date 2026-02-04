import sys
import requests
from bs4 import BeautifulSoup

response = requests.get("https://hoe.com.ua/page/pogodinni-vidkljuchennja")
soup = BeautifulSoup(response.text, 'html.parser')
content = soup.find('div', class_='content-main')

if content:
    first_img = content.find('img')
    for el in content.find_all(['p', 'li', 'ul']):
        if first_img and el.find('img'):
            break
        txt = el.get_text(strip=True)
        if 'черг' in txt.lower() and len(txt) > 20:
            print(txt)
            print('=' * 80)

import os
import re
import time
import threading
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

# Kayıt klasörü
os.makedirs("recordings", exist_ok=True)

# İstanbul UŞEYT ana sayfa
BASE_URL = "https://istanbuluseyret.ibb.gov.tr/kameralar/"

# Tüm kamera sayfalarını al
def get_camera_links():
    r = requests.get(BASE_URL)
    soup = BeautifulSoup(r.text, "html.parser")
    links = soup.select(".iconbox_content_title a")
    cameras = {link.text.strip(): link.get("href") for link in links}
    return cameras

# Kamera sayfasından m3u8 linkini al (JS objesi içinden)
def get_m3u8_from_page(page_url):
    r = requests.get(page_url)
    html = r.text
    # bradmaxPlayerConfig JS objesinden URL al
    m = re.search(r'"url":"(https:\\/\\/livestream\.ibb\.gov\.tr\\/.*?\.m3u8)"', html)
    if m:
        return m.group(1).replace("\\/", "/")
    return None

# 1 dakikalık kaydı al
def record(name, m3u8_url):
    while True:
        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=60)
        filename = f"recordings/{name}_{start_time.strftime('%H%M%S')}_{end_time.strftime('%H%M%S')}.ts"
        print(f"Kayıt başlıyor: {filename}")
        os.system(f'ffmpeg -y -i "{m3u8_url}" -t 60 -c copy "{filename}"')
        time.sleep(1)

if __name__ == "__main__":
    cameras = get_camera_links()
    threads = []
    print(f"Toplam kamera bulundu: {len(cameras)}")
    for name, page_url in cameras.items():
        m3u8 = get_m3u8_from_page(page_url)
        if m3u8:
            print(f"{name}: {m3u8}")
            t = threading.Thread(target=record, args=(name, m3u8))
            t.start()
            threads.append(t)
        else:
            print(f"{name} için m3u8 bulunamadı!")

    for t in threads:
        t.join()

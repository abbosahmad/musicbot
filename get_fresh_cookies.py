#!/usr/bin/env python3
# get_fresh_cookies.py - Yangi cookies olish

import os
import subprocess
import time

def get_cookies_with_browser():
    """
    Brauzer orqali yangi cookies olish
    """
    print("🍪 Yangi cookies olish jarayoni:")
    print("=" * 40)
    
    print("1️⃣ VPN yoqing (agar bor bo'lsa)")
    print("2️⃣ YouTube.com ga kiring")
    print("3️⃣ Bir nechta video ko'ring (5-10 daqiqa)")
    print("4️⃣ Quyidagi buyruqni ishga tushiring:")
    
    browsers = ['chrome', 'firefox', 'edge']
    
    for browser in browsers:
        print(f"\n🔧 {browser.title()} uchun:")
        print(f"yt-dlp --cookies-from-browser {browser} --print-to-file webpage_url cookies_test.txt \"ytsearch1:test\"")
    
    print("\n5️⃣ Agar muvaffaqiyatli bo'lsa, cookies.txt ni yangilang")
    
    input("\nTayyor bo'lgach Enter bosing...")
    
    # Test qilish
    for browser in browsers:
        try:
            print(f"\n🧪 {browser.title()} test qilinmoqda...")
            
            cmd = [
                'yt-dlp', 
                '--cookies-from-browser', browser,
                '--quiet',
                '--print', 'title',
                'ytsearch1:test music'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and result.stdout.strip():
                print(f"✅ {browser.title()} ishlaydi!")
                
                # Cookies ni saqlash
                cmd_save = [
                    'yt-dlp',
                    '--cookies-from-browser', browser,
                    '--cookies', 'cookies_new.txt',
                    '--quiet',
                    '--print', 'title',
                    'ytsearch1:test music'
                ]
                
                subprocess.run(cmd_save, timeout=30)
                
                if os.path.exists('cookies_new.txt'):
                    # Eski cookies ni zaxiralash
                    if os.path.exists('cookies.txt'):
                        os.rename('cookies.txt', 'cookies_old.txt')
                    
                    os.rename('cookies_new.txt', 'cookies.txt')
                    print("💾 Yangi cookies saqlandi!")
                    return True
                    
            else:
                print(f"❌ {browser.title()}: {result.stderr}")
                
        except Exception as e:
            print(f"❌ {browser.title()}: {e}")
    
    return False

if __name__ == "__main__":
    get_cookies_with_browser()
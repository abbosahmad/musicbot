#!/usr/bin/env python3
# fix_youtube.py - YouTube cookies muammosini hal qilish

import os
import time
import subprocess
import yt_dlp

def method_1_browser_cookies():
    """
    Usul 1: Brauzerdan to'g'ridan-to'g'ri cookies olish
    """
    print("🔧 Usul 1: Brauzer cookies")
    
    browsers = ['chrome', 'firefox', 'edge']
    
    for browser in browsers:
        try:
            print(f"🔍 {browser.title()} tekshirilmoqda...")
            
            ydl_opts = {
                'cookiesfrombrowser': (browser,),
                'quiet': True,
                'extract_flat': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Test qilish
                result = ydl.extract_info("ytsearch1:test", download=False)
                if result and 'entries' in result and result['entries']:
                    print(f"✅ {browser.title()} cookies ishlaydi!")
                    
                    # Cookies ni faylga saqlash
                    save_opts = {
                        'cookiesfrombrowser': (browser,),
                        'cookiefile': 'cookies_new.txt',
                        'quiet': True,
                    }
                    
                    with yt_dlp.YoutubeDL(save_opts) as ydl_save:
                        ydl_save.extract_info("ytsearch1:test", download=False)
                    
                    if os.path.exists('cookies_new.txt'):
                        # Eski cookies ni zaxiralash
                        if os.path.exists('cookies.txt'):
                            os.rename('cookies.txt', 'cookies_backup.txt')
                        
                        # Yangi cookies ni o'rnatish
                        os.rename('cookies_new.txt', 'cookies.txt')
                        print("💾 Yangi cookies saqlandi!")
                        return True
                        
        except Exception as e:
            print(f"❌ {browser.title()}: {e}")
            continue
    
    return False

def method_2_manual_cookies():
    """
    Usul 2: Qo'lda cookies kiritish
    """
    print("\n🔧 Usul 2: Qo'lda cookies")
    print("1. YouTube.com ga kiring")
    print("2. F12 bosing (Developer Tools)")
    print("3. Application/Storage tab ga o'ting")
    print("4. Cookies > youtube.com ni tanlang")
    print("5. Barcha cookies'larni copy qiling")
    print("6. cookies.txt ga joylashtiring")
    
    return False

def method_3_proxy_rotation():
    """
    Usul 3: Proxy/VPN ishlatish
    """
    print("\n🔧 Usul 3: Proxy/VPN")
    print("1. VPN yoqing")
    print("2. IP manzilni o'zgartiring")
    print("3. Yangi IP bilan cookies oling")
    
    return False

def method_4_alternative_sources():
    """
    Usul 4: Boshqa manbalar
    """
    print("\n🔧 Usul 4: Boshqa manbalar")
    print("YouTube o'rniga boshqa audio manbalardan foydalanish:")
    print("- SoundCloud")
    print("- Spotify (metadata)")
    print("- Deezer")
    
    return False

def test_current_cookies():
    """
    Hozirgi cookies'ni test qilish
    """
    print("🧪 Hozirgi cookies test qilinmoqda...")
    
    if not os.path.exists('cookies.txt'):
        print("❌ cookies.txt topilmadi")
        return False
    
    try:
        ydl_opts = {
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'extract_flat': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info("ytsearch1:test music", download=False)
            
            if result and 'entries' in result and result['entries']:
                print("✅ Hozirgi cookies ishlaydi!")
                return True
            else:
                print("❌ Cookies ishlamaydi")
                return False
                
    except Exception as e:
        print(f"❌ Cookies test xatosi: {e}")
        return False

def main():
    print("🚀 YouTube Cookies Muammosini Hal Qilish")
    print("=" * 50)
    
    # Hozirgi holatni tekshirish
    if test_current_cookies():
        print("✅ Cookies allaqachon ishlaydi!")
        return
    
    print("\n🔧 Muammoni hal qilish usullari:")
    
    # Usul 1: Brauzer cookies
    if method_1_browser_cookies():
        print("✅ Muammo hal qilindi!")
        return
    
    # Boshqa usullar
    method_2_manual_cookies()
    method_3_proxy_rotation()
    method_4_alternative_sources()
    
    print("\n💡 Tavsiya:")
    print("1. VPN yoqing")
    print("2. YouTube.com ga kiring")
    print("3. Bir nechta video ko'ring")
    print("4. Qaytadan cookies oling")

if __name__ == "__main__":
    main()
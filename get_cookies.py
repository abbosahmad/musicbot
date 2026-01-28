#!/usr/bin/env python3
# get_cookies.py - YouTube cookies olish

import yt_dlp
import os

def get_fresh_cookies():
    """
    Brauzerdan yangi cookies olish
    """
    print("🍪 YouTube cookies yangilanmoqda...")
    
    # Eski cookies.txt ni zaxiralash
    if os.path.exists('cookies.txt'):
        os.rename('cookies.txt', 'cookies_backup.txt')
        print("📦 Eski cookies zaxiralandi")
    
    # Brauzerdan cookies olish
    browsers = ['chrome', 'firefox', 'edge', 'safari']
    
    for browser in browsers:
        try:
            print(f"🔍 {browser.title()} brauzeridan cookies olinmoqda...")
            
            ydl_opts = {
                'cookiesfrombrowser': (browser,),
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Test qilish uchun biror video
                test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                info = ydl.extract_info(test_url, download=False)
                
                if info:
                    print(f"✅ {browser.title()} dan cookies muvaffaqiyatli olindi!")
                    
                    # Cookies ni faylga saqlash
                    ydl_opts_save = {
                        'cookiesfrombrowser': (browser,),
                        'cookiefile': 'cookies.txt',
                        'quiet': True,
                    }
                    
                    with yt_dlp.YoutubeDL(ydl_opts_save) as ydl_save:
                        ydl_save.extract_info(test_url, download=False)
                    
                    print("💾 Cookies cookies.txt ga saqlandi")
                    return True
                    
        except Exception as e:
            print(f"❌ {browser.title()}: {e}")
            continue
    
    print("❌ Hech qaysi brauzerdan cookies olinmadi")
    
    # Eski cookies ni qaytarish
    if os.path.exists('cookies_backup.txt'):
        os.rename('cookies_backup.txt', 'cookies.txt')
        print("🔄 Eski cookies qaytarildi")
    
    return False

def test_cookies():
    """
    Cookies ni test qilish
    """
    print("\n🧪 Cookies test qilinmoqda...")
    
    ydl_opts = {
        'cookiefile': 'cookies.txt',
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Qidiruv test
            results = ydl.extract_info("ytsearch:test music", download=False)
            
            if results and 'entries' in results and results['entries']:
                print("✅ Cookies ishlayapti! YouTube qidiruv muvaffaqiyatli")
                return True
            else:
                print("❌ Qidiruv natijasi yo'q")
                return False
                
    except Exception as e:
        print(f"❌ Cookies test xatosi: {e}")
        return False

if __name__ == "__main__":
    print("🚀 YouTube Cookies Yangilash Vositasi")
    print("=" * 40)
    
    # Cookies olish
    success = get_fresh_cookies()
    
    if success:
        # Test qilish
        test_cookies()
    else:
        print("\n💡 Qo'lda cookies olish:")
        print("1. YouTube.com ga kiring")
        print("2. Brauzer Developer Tools (F12) oching")
        print("3. Network tab ga o'ting")
        print("4. Biror video ochib, cookies ni export qiling")
        print("5. cookies.txt ga joylashtiring")
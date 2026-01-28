#!/usr/bin/env python3
# test_youtube_download.py - YouTube yuklashni test qilish

import utils
import asyncio

async def test_youtube():
    print("🧪 YouTube yuklash test qilinmoqda...")
    
    # Test ma'lumotlari
    test_cases = [
        ("Mirjalol Nematov", "So'zim yo'q", 180),
        ("Yulduz Usmonova", "Layli", 200),
        ("Shoxrux", "Yor yor", 160),
    ]
    
    for artist, title, duration in test_cases:
        print(f"\n🎵 Test: {artist} - {title}")
        
        try:
            result = utils.download_best_match_from_youtube(artist, title, duration)
            
            if result:
                print(f"✅ Muvaffaqiyat: {result}")
                # Faylni o'chirish
                import os
                if os.path.exists(result):
                    os.remove(result)
                    print("🗑️ Test fayl o'chirildi")
            else:
                print("❌ Yuklash muvaffaqiyatsiz")
                
        except Exception as e:
            print(f"❌ Xato: {e}")

if __name__ == "__main__":
    asyncio.run(test_youtube())
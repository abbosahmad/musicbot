from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import uvicorn
import database
import config
from loguru import logger
import os

app = FastAPI()

# Shablonlar papkasini yaratish (agar bo'lmasa)
if not os.path.exists("templates"):
    os.makedirs("templates")

templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    settings = database.get_all_settings()
    return templates.TemplateResponse("index.html", {"request": request, "settings": settings})

@app.post("/update")
async def update_settings(
    request: Request,
    planning_hour: str = Form(...),
    daily_post_count: str = Form(...),
    source_channels: str = Form(...),
    demo_duration: str = Form(...),
    night_mode: str = Form(None), # Checkbox belgilanmasa None keladi
    night_start: str = Form(...),
    night_end: str = Form(...)
):
    database.set_setting("planning_hour", planning_hour)
    database.set_setting("daily_post_count", daily_post_count)
    database.set_setting("source_channels", source_channels)
    database.set_setting("demo_duration", demo_duration)
    
    # Tun rejimi logikasi
    is_night_mode = "true" if night_mode else "false"
    database.set_setting("night_mode", is_night_mode)
    database.set_setting("night_start", night_start)
    database.set_setting("night_end", night_end)
    
    logger.success(f"Web App orqali sozlamalar o'zgartirildi (Tun rejimi: {is_night_mode}).")
    
    # Muvaffaqiyatli saqlanganini ko'rsatib, bosh sahifaga qaytish
    return RedirectResponse(url="/?saved=true", status_code=303)

def run_web_app():
    # 8000 portda ishga tushadi
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")

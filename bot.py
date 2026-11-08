#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Python rewrite of the Numberino virtual-number Telegram bot.

The application uses SQLite, the Telegram Bot API, 5sim-compatible SMS API,
Inax prepaid top-up API and SenatorOzv member API. All credentials are read
from environment variables; no credentials from the PHP source are embedded.
"""
from __future__ import annotations

import asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
import json
import logging
import math
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from dotenv import load_dotenv
from telegram import Bot, Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
try:
    _legacy_cfg=json.loads((DATA_DIR/"seting.json").read_text(encoding="utf-8"))
    _legacy_set=_legacy_cfg.get("set",{})
except Exception:
    _legacy_set={}
DB_PATH = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "numberino.sqlite3")))
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {int(x) for x in re.split(r"[,; ]+", os.getenv("ADMIN_IDS", "")) if x.isdigit()}
CHANNEL = os.getenv("CHANNEL", str(_legacy_set.get("channel", ""))).strip().lstrip("@")
REPORT_CHANNEL = os.getenv("REPORT_CHANNEL", "").strip()
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "").strip().lstrip("@")
FIVESIM_KEY = os.getenv("FIVESIM_API_KEY", "").strip()
FIVESIM_BASE = os.getenv("FIVESIM_BASE_URL", "http://api1.5sim.net/stubs/handler_api.php").rstrip("/")
INAX_USER = os.getenv("INAX_USERNAME", "").strip()
INAX_PASS = os.getenv("INAX_PASSWORD", "").strip()
SENATOR_KEY = os.getenv("SENATOR_API_KEY", "").strip()
ROUBLE_RATE = int(os.getenv("ROUBLE_RATE", str(_legacy_set.get("robelpric", "600"))))
DEFAULT_MARKUP = float(os.getenv("DEFAULT_MARKUP", str(ROUBLE_RATE)))
MEMBER_MARKUP = float(os.getenv("MEMBER_MARKUP", str(_legacy_set.get("memberpric", "10"))))
GOLD_BOT_PRICE = int(os.getenv("GOLD_BOT_PRICE", str(_legacy_set.get("pricbottala", "10000"))))
SILVER_BOT_PRICE = int(os.getenv("SILVER_BOT_PRICE", str(_legacy_set.get("pricbotn", "0"))))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
PAYMENT_MERCHANT_ID = os.getenv("ZARINPAL_MERCHANT_ID", "").strip()
PORT = int(os.getenv("PORT", "8080"))
POLL_SECONDS = max(3, int(os.getenv("SMS_POLL_SECONDS", "5")))
SMS_TIMEOUT = max(60, int(os.getenv("SMS_TIMEOUT_SECONDS", "420")))

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("numberino")

SERVICE_LABELS = {
    "instagram":"اینستاگرام", "telegram":"تلگرام", "whatsapp":"واتساپ", "wechat":"وی‌چت", "viber":"وایبر", "twitter":"توییتر", "line":"لاین", "imo":"ایمو", "facebook":"فیسبوک", "google":"گوگل", "yahoo":"یاهو", "discord":"دیسکورد", "amazon":"آمازون", "alibaba":"علی‌بابا", "alipay":"علی‌پی", "bigolive":"بیگو لایو", "linkedin":"لینکدین", "microsoft":"مایکروسافت", "paypal":"پی‌پال", "snapchat":"اسنپ‌چت", "tiktok":"تیک‌تاک", "digikala":"دیجی‌کالا", "divar":"دیوار", "hamrahaval":"همراه اول", "irancell":"ایرانسل", "pubg":"پابجی", "blockchain":"بلاکچین", "tango":"تانگو", "1688":"1688", "1xbet":"1xbet", "23red":"23red", "steam":"استیم", "signal":"سیگنال", "tinder":"تندر", "uber":"اوبر", "netflix":"نتفلیکس", "other":"سایر سرویس‌ها"
}
COUNTRY_LABELS = {
    "afghanistan":"افغانستان", "albania":"آلبانی", "algeria":"الجزایر", "argentina":"آرژانتین", "armenia":"ارمنستان", "australia":"استرالیا", "austria":"اتریش", "azerbaijan":"آذربایجان", "bahrain":"بحرین", "bangladesh":"بنگلادش", "belarus":"بلاروس", "belgium":"بلژیک", "brazil":"برزیل", "canada":"کانادا", "china":"چین", "colombia":"کلمبیا", "czech":"چک", "denmark":"دانمارک", "egypt":"مصر", "england":"انگلیس", "finland":"فنلاند", "france":"فرانسه", "georgia":"گرجستان", "germany":"آلمان", "ghana":"غنا", "greece":"یونان", "india":"هند", "indonesia":"اندونزی", "iran":"ایران", "iraq":"عراق", "ireland":"ایرلند", "israel":"اسرائیل", "italy":"ایتالیا", "japan":"ژاپن", "kazakhstan":"قزاقستان", "kenya":"کنیا", "kuwait":"کویت", "malaysia":"مالزی", "mexico":"مکزیک", "netherlands":"هلند", "newzealand":"نیوزیلند", "nigeria":"نیجریه", "norway":"نروژ", "oman":"عمان", "pakistan":"پاکستان", "poland":"لهستان", "portugal":"پرتغال", "qatar":"قطر", "romania":"رومانی", "russia":"روسیه", "saudiarabia":"عربستان", "serbia":"صربستان", "singapore":"سنگاپور", "southafrica":"آفریقای جنوبی", "spain":"اسپانیا", "sweden":"سوئد", "switzerland":"سوئیس", "taiwan":"تایوان", "tajikistan":"تاجیکستان", "thailand":"تایلند", "turkey":"ترکیه", "uae":"امارات", "ukraine":"اوکراین", "usa":"آمریکا", "uzbekistan":"ازبکستان", "vietnam":"ویتنام"
}
MAIN_MENU = [
    ["📲 خرید شماره مجازی"],
    ["✔️ خدمات سیمکارت اعتباری", "✔️ خدمات تلگرام"],
    ["💳 استعلام | قیمت ها", "💸 شارژ حساب"],
    ["🤖 ربات شماره مجازی شما [ربات نمایندگی]"],
    ["💻 پنل فروش"],
    ["👥 زیرمجموعه گیری"],
    ["🛍 خرید های من", "👤 اطلاعات حساب"],
    ["👮🏻 پشتیبانی", "🚦 راهنما"],
]
ADMIN_MENU = [
    ["📍 امار ربات", "📍 شارژ پنل"], ["📍 ارسال پیام", "👥 مدیریت کاربران"],
    ["⛔️ توقف فروش", "❎ شروع فروش"], ["⛔️ توقف فروش نمایندگی ها", "❎ شروع فروش نمایندگی ها"],
    ["💸 تعیین قیمت روبل", "💸 تعیین قیمت ممبر"], ["💸 پورسانت زیر مجموعه گیری 👥", "📍 لیست نمایندگی ها"],
    ["💸 تعیین مبلغ ربات نقره‌ای", "📍تعیین مبلغ خرید ربات طلایی"],
    ["🛒 شارژهای فروخته شده", "💵 پرداختی های ربات"], ["☑️ پیگیری سفارش ممبر"],
    ["📍 افزایش | کاهش موجودی پنل طلایی"], ["💳 پیگیری پرداخت"], ["📢 تنظیم کانال ربات"], ["خروج از پنل"]
]


def gregorian_to_jalali(gy:int,gm:int,gd:int) -> tuple[int,int,int]:
    gdm=[0,31,59,90,120,151,181,212,243,273,304,334]
    gy2=gy+1 if gm>2 else gy
    days=355666+365*gy+(gy2+3)//4-(gy2+99)//100+(gy2+399)//400+gd+gdm[gm-1]
    jy=-1595+33*(days//12053)
    days%=12053
    jy+=4*(days//1461)
    days%=1461
    if days>365:
        jy+=(days-1)//365
        days=(days-1)%365
    if days<186: jm=1+days//31; jd=1+days%31
    else: jm=7+(days-186)//30; jd=1+(days-186)%30
    return jy,jm,jd


def now_text() -> str:
    current=datetime.now(ZoneInfo("Asia/Tehran"))
    jy,jm,jd=gregorian_to_jalali(current.year,current.month,current.day)
    return f"{jy:04d}/{jm:02d}/{jd:02d} {current:%H:%M:%S}"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def db_connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30, factory=ClosingConnection)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    with db_connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          bot_key TEXT NOT NULL DEFAULT 'main', user_id INTEGER NOT NULL, username TEXT DEFAULT '', first_name TEXT DEFAULT '',
          step TEXT DEFAULT 'none', balance REAL NOT NULL DEFAULT 0, referrals INTEGER NOT NULL DEFAULT 0,
          inviter INTEGER DEFAULT 0, service TEXT DEFAULT '', country TEXT DEFAULT '', country_name TEXT DEFAULT '',
          operator TEXT DEFAULT '', active_order TEXT DEFAULT '', active_number TEXT DEFAULT '', active_price REAL DEFAULT 0,
          purchases INTEGER NOT NULL DEFAULT 0, purchase_history TEXT DEFAULT '', created_at INTEGER NOT NULL,
          blocked INTEGER NOT NULL DEFAULT 0, sim_amount INTEGER DEFAULT 0, sim_mode TEXT DEFAULT '',
          sim_charge_type TEXT DEFAULT '', sim_mobile TEXT DEFAULT '', reseller_type TEXT DEFAULT '',
          referral_join_paid INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(bot_key,user_id));
        CREATE TABLE IF NOT EXISTS orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, bot_key TEXT NOT NULL, user_id INTEGER NOT NULL, provider_id TEXT,
          service TEXT, country TEXT, country_name TEXT, phone TEXT, price REAL NOT NULL DEFAULT 0, base_price REAL NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'pending', sms_code TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(bot_key,user_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, bot_key TEXT NOT NULL, user_id INTEGER NOT NULL, amount REAL NOT NULL,
          kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', reference TEXT UNIQUE, created_at INTEGER NOT NULL, payload TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS blacklist(bot_key TEXT NOT NULL,user_id INTEGER NOT NULL,reason TEXT DEFAULT '',created_at INTEGER NOT NULL,PRIMARY KEY(bot_key,user_id));
        CREATE TABLE IF NOT EXISTS member_orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT, bot_key TEXT NOT NULL,user_id INTEGER NOT NULL,provider_id TEXT,
          product_id TEXT,product_name TEXT,link TEXT,count INTEGER,price REAL,status TEXT DEFAULT 'pending',created_at INTEGER);
        CREATE TABLE IF NOT EXISTS recharge_orders(
          id INTEGER PRIMARY KEY AUTOINCREMENT,bot_key TEXT NOT NULL,user_id INTEGER NOT NULL,operator TEXT,mobile TEXT,
          amount INTEGER,charge_type TEXT,provider_ref TEXT,status TEXT DEFAULT 'pending',created_at INTEGER);
        CREATE TABLE IF NOT EXISTS reseller_bots(
          token TEXT PRIMARY KEY, bot_username TEXT UNIQUE, owner_id INTEGER NOT NULL, active INTEGER DEFAULT 1,
          markup REAL DEFAULT 600, channel TEXT DEFAULT '', created_at INTEGER NOT NULL,
          earnings REAL NOT NULL DEFAULT 0, sales_total REAL NOT NULL DEFAULT 0, order_count INTEGER NOT NULL DEFAULT 0,
          bot_type TEXT DEFAULT 'silver', parent_bot_key TEXT DEFAULT 'main', panel_balance REAL NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reseller_settings(bot_key TEXT NOT NULL,key TEXT NOT NULL,value TEXT NOT NULL,PRIMARY KEY(bot_key,key));
        CREATE TABLE IF NOT EXISTS api_keys(
          api_key TEXT PRIMARY KEY, owner_id INTEGER NOT NULL, balance REAL DEFAULT 0, active INTEGER DEFAULT 1, created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS api_numbers(
          provider_id TEXT PRIMARY KEY, api_key TEXT NOT NULL, phone TEXT, status TEXT DEFAULT 'pending', expires_at INTEGER);
        CREATE TABLE IF NOT EXISTS payout_requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT, bot_username TEXT NOT NULL, owner_id INTEGER NOT NULL,
          amount REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS support_messages(
          id INTEGER PRIMARY KEY AUTOINCREMENT, bot_key TEXT NOT NULL,user_id INTEGER NOT NULL,
          question TEXT NOT NULL,answer TEXT DEFAULT '',status TEXT DEFAULT 'pending',created_at INTEGER NOT NULL,answered_at INTEGER);
        """)
        defaults = {
          "sales_active":str(_legacy_set.get("active","1")), "reseller_sales_active":str(_legacy_set.get("activebots","0")), "rouble_rate":str(ROUBLE_RATE),
          "markup":str(DEFAULT_MARKUP), "referral_percent":"10", "referral_join_reward":str(_legacy_set.get("porsant","50")), "member_markup":str(MEMBER_MARKUP),
          "member_enabled":"1", "sim_enabled":"1", "main_channel":CHANNEL,
          "support_username":SUPPORT_USERNAME, "report_channel":REPORT_CHANNEL,
          "welcome_text":"😄 سلام {name}\n\n🌟 به ربات خرید شماره مجازی خوش آمدید.\n\nاز دکمه‌های زیر استفاده کنید.",
          "gold_bot_price":str(GOLD_BOT_PRICE), "silver_bot_price":str(SILVER_BOT_PRICE)
        }
        for k,v in defaults.items(): c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
        # Additive migrations for databases created by earlier builds.
        migrations={
          "users":{"sim_amount":"INTEGER DEFAULT 0","sim_mode":"TEXT DEFAULT ''","sim_charge_type":"TEXT DEFAULT ''","sim_mobile":"TEXT DEFAULT ''","reseller_type":"TEXT DEFAULT ''","referral_join_paid":"INTEGER NOT NULL DEFAULT 0"},
          "orders":{"base_price":"REAL NOT NULL DEFAULT 0"},
          "reseller_bots":{"earnings":"REAL NOT NULL DEFAULT 0","sales_total":"REAL NOT NULL DEFAULT 0","order_count":"INTEGER NOT NULL DEFAULT 0","bot_type":"TEXT DEFAULT 'silver'","parent_bot_key":"TEXT DEFAULT 'main'","panel_balance":"REAL NOT NULL DEFAULT 0"}
        }
        for table,cols in migrations.items():
            existing={r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}
            for col,definition in cols.items():
                if col not in existing: c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")


def setting(key: str, default: str = "", bot_key: str = "main") -> str:
    with db_connect() as c:
        if bot_key != "main":
            r=c.execute("SELECT value FROM reseller_settings WHERE bot_key=? AND key=?",(bot_key,key)).fetchone()
            if r: return str(r[0])
        r = c.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        return str(r[0]) if r else default


def set_setting(key: str, value: Any, bot_key: str = "main") -> None:
    with db_connect() as c:
        if bot_key != "main":
            c.execute("INSERT INTO reseller_settings(bot_key,key,value) VALUES(?,?,?) ON CONFLICT(bot_key,key) DO UPDATE SET value=excluded.value",(bot_key,key,str(value)))
        else:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,str(value)))


def get_user(bot_key: str, uid: int) -> sqlite3.Row | None:
    with db_connect() as c: return c.execute("SELECT * FROM users WHERE bot_key=? AND user_id=?",(bot_key,uid)).fetchone()


def ensure_user(bot_key: str, u: Any, inviter: int = 0) -> sqlite3.Row:
    with db_connect() as c:
        c.execute("INSERT OR IGNORE INTO users(bot_key,user_id,username,first_name,inviter,created_at) VALUES(?,?,?,?,?,?)",(bot_key,u.id,u.username or "",u.first_name or "",inviter,int(time.time())))
        c.execute("UPDATE users SET username=?,first_name=? WHERE bot_key=? AND user_id=?",(u.username or "",u.first_name or "",bot_key,u.id))
        return c.execute("SELECT * FROM users WHERE bot_key=? AND user_id=?",(bot_key,u.id)).fetchone()


def update_user(bot_key: str, uid: int, **fields: Any) -> None:
    if not fields: return
    allowed={"step","balance","referrals","inviter","service","country","country_name","operator","active_order","active_number","active_price","purchases","purchase_history","blocked","sim_amount","sim_mode","sim_charge_type","sim_mobile","reseller_type"}
    fields={k:v for k,v in fields.items() if k in allowed}
    if not fields: return
    sql=", ".join(f"{k}=?" for k in fields)
    with db_connect() as c: c.execute(f"UPDATE users SET {sql} WHERE bot_key=? AND user_id=?",(*fields.values(),bot_key,uid))


def money(n: float) -> str: return f"{int(round(n)):,}"


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(x) for x in row] for row in MAIN_MENU],resize_keyboard=True)


def admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([[KeyboardButton(x) for x in row] for row in ADMIN_MENU],resize_keyboard=True)


def is_admin(uid: int, bot_key: str = "main") -> bool:
    if uid in ADMIN_IDS: return True
    if bot_key != "main":
        with db_connect() as c:
            r=c.execute("SELECT owner_id FROM reseller_bots WHERE bot_username=? AND active=1",(bot_key.split(":",1)[-1],)).fetchone()
            return bool(r and int(r[0])==uid)
    return False


def reseller_admin_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([["📊 آمار ربات من"],["💳 شارژ پنل"],["💸 درخواست تسفیه"],["💸 تعیین ضریب قیمت"],["📢 تنظیم کانال"],["📍 ارسال پیام همگانی"],["❎ شروع فروش","⛔️ توقف فروش"],["خروج از پنل"]],resize_keyboard=True)


def is_reseller_bot(bot_key: str) -> bool: return bot_key != "main"


def bot_key_of(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.application.bot_data.get("bot_key","main")


async def http_get(url: str, params: dict | None = None, timeout: float = 20) -> str:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        r=await client.get(url,params=params); r.raise_for_status(); return r.text.strip()


async def five_sim(action: str, **params: Any) -> str:
    if not FIVESIM_KEY: raise RuntimeError("کلید پنل شماره مجازی تنظیم نشده است")
    q={"api_key":FIVESIM_KEY,"action":action,**params}
    return await http_get(FIVESIM_BASE,q,25)


async def five_prices(country: str | None = None, service: str | None = None) -> dict:
    raw=await five_sim("getPrices",**({"country":country} if country else {}),**({"service":service} if service else {}))
    try: return json.loads(raw)
    except json.JSONDecodeError: raise RuntimeError(f"پاسخ نامعتبر پنل قیمت: {raw[:160]}")


def available_countries(prices: dict, service: str) -> list[tuple[str,dict]]:
    result=[]
    for country, services in prices.items():
        s=services.get(service) if isinstance(services,dict) else None
        if not isinstance(s,dict): continue
        ops=[v for v in s.values() if isinstance(v,dict) and float(v.get("cost") or 0)>0 and int(v.get("count") or 0)>0]
        if ops: result.append((country,s))
    return sorted(result,key=lambda x: min(float(v.get("cost") or 999999) for v in x[1].values() if isinstance(v,dict) and float(v.get("cost") or 0)>0 and int(v.get("count") or 0)>0))


def price_rate(bot_key: str) -> float:
    key="markup" if bot_key != "main" else "rouble_rate"
    default=DEFAULT_MARKUP if bot_key != "main" else ROUBLE_RATE
    try:
        value=max(1.0,float(setting(key,str(default),bot_key)))
        if bot_key!="main": value=max(value,float(setting("rouble_rate",ROUBLE_RATE,"main")))
        return value
    except (TypeError,ValueError): return float(default)


def choose_operator(data: dict, markup: float) -> tuple[str,float,int] | None:
    candidates=[]
    for op,v in data.items():
        if not isinstance(v,dict): continue
        try: cost=float(v.get("cost") or 0); count=int(v.get("count") or 0)
        except (TypeError,ValueError): continue
        if cost>0 and count>0: candidates.append((op,math.ceil(cost*markup),count,cost))
    if not candidates: return None
    op,price,count,_=min(candidates,key=lambda x:x[1])
    return op,float(price),count


def service_label(code: str) -> str:
    return SERVICE_LABELS.get(code,code.replace("_"," ").title())


def country_label(code: str) -> str:
    return COUNTRY_LABELS.get(code,code.replace("_"," ").title())


def load_services() -> list[str]:
    found=set(SERVICE_LABELS)
    for p in (DATA_DIR/"prics2").glob("*.json"):
        try: found.update(json.loads(p.read_text(encoding="utf-8")).keys())
        except Exception: pass
    return sorted(found)

SERVICES=load_services()


def page_keyboard(items: list[tuple[str,str]], prefix: str, page: int, per_page: int=24) -> InlineKeyboardMarkup:
    start=page*per_page; chunk=items[start:start+per_page]
    rows=[]
    for i in range(0,len(chunk),2):
        row=[InlineKeyboardButton(chunk[j][1],callback_data=f"{prefix}:{chunk[j][0]}") for j in range(i,min(i+2,len(chunk)))]
        rows.append(row)
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("⬅️ قبلی",callback_data=f"{prefix}page:{page-1}"))
    if start+per_page<len(items): nav.append(InlineKeyboardButton("بعدی ➡️",callback_data=f"{prefix}page:{page+1}"))
    if nav: rows.append(nav)
    rows.append([InlineKeyboardButton("✖️ بستن",callback_data="close")])
    return InlineKeyboardMarkup(rows)


async def award_referral_join(bot,bot_key: str,uid: int) -> None:
    if not setting("main_channel",CHANNEL,bot_key): return
    with db_connect() as c:
        user=c.execute("SELECT inviter,referral_join_paid FROM users WHERE bot_key=? AND user_id=?",(bot_key,uid)).fetchone()
        if not user or not int(user["inviter"] or 0) or int(user["referral_join_paid"] or 0): return
        inviter=int(user["inviter"]); reward=float(setting("referral_join_reward","50",bot_key))
        c.execute("UPDATE users SET referral_join_paid=1 WHERE bot_key=? AND user_id=? AND referral_join_paid=0",(bot_key,uid))
        if reward>0:
            c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(reward,bot_key,inviter))
            c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(bot_key,inviter,reward,"referral_join","success",f"refjoin-{uid}-{bot_key}",int(time.time()),str(uid)))
    if reward>0:
        try: await bot.send_message(inviter,f"🎁 زیرمجموعه شما عضو کانال شد؛ {money(reward)} تومان پاداش به کیف پول شما اضافه شد.")
        except Exception: pass


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    bot_key=bot_key_of(context); u=update.effective_user
    inviter=0
    if context.args and context.args[0].isdigit(): inviter=int(context.args[0])
    old=get_user(bot_key,u.id)
    row=ensure_user(bot_key,u,inviter if inviter!=u.id else 0)
    if not old and inviter and inviter!=u.id:
        ref=get_user(bot_key,inviter)
        if ref:
            with db_connect() as c: c.execute("UPDATE users SET referrals=referrals+1 WHERE bot_key=? AND user_id=?",(bot_key,inviter))
            try: await context.bot.send_message(inviter,f"👥 یک کاربر با لینک دعوت شما وارد ربات شد. تعداد زیرمجموعه‌ها: {int(ref['referrals'])+1}")
            except Exception: pass
    if int(row["blocked"] or 0):
        await update.effective_message.reply_text("دسترسی شما به ربات مسدود شده است."); return
    if not await check_join(update,context): return
    await award_referral_join(context.bot,bot_key,u.id)
    text=setting("welcome_text",bot_key=bot_key).format(name=u.first_name or "دوست")
    await update.effective_message.reply_text(text,reply_markup=main_keyboard())


async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    channel=setting("main_channel",CHANNEL,bot_key_of(context))
    if not channel: return True
    uid=update.effective_user.id
    try:
        m=await context.bot.get_chat_member("@"+channel.lstrip("@"),uid)
        if m.status in ("member","administrator","creator"): return True
    except Exception as e: log.warning("channel membership check: %s",e)
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("📢 عضویت در کانال",url=f"https://t.me/{channel.lstrip('@')}")],[InlineKeyboardButton("📢 عضو شدم",callback_data="joincheck")]])
    await update.effective_message.reply_text("برای استفاده از ربات ابتدا در کانال عضو شو و بعد روی «عضو شدم» بزن.",reply_markup=kb)
    return False


async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int=0, edit: bool=False) -> None:
    items=[(s,f"💠 {service_label(s)}") for s in SERVICES]
    text="🔘 سرویس مورد نظر برای دریافت شماره را انتخاب کن:"
    if edit and update.callback_query: await update.callback_query.edit_message_text(text,reply_markup=page_keyboard(items,"svc",page,24))
    else: await update.effective_message.reply_text(text,reply_markup=page_keyboard(items,"svc",page,24))


async def show_countries(q, context, service: str, page: int=0) -> None:
    await q.edit_message_text("در حال دریافت قیمت و موجودی کشورها…")
    try: prices=await five_prices(service=service)
    except Exception as e: await q.edit_message_text(f"خطا در دریافت قیمت‌ها: {e}"); return
    countries=available_countries(prices,service)
    if not countries: await q.edit_message_text("برای این سرویس در حال حاضر شماره موجود نیست."); return
    markup=price_rate(bot_key_of(context))
    items=[]
    for code,data in countries:
        chosen=choose_operator(data,markup)
        if chosen:
            _,cost,count=chosen
            items.append((code,f"🌍 {country_label(code)} | {money(cost)} تومان | {count} عدد"))
    context.user_data["country_items"]=items
    context.user_data["selected_service"]=service
    context.user_data["price_cache"]={k:v for k,v in prices.items()}
    await q.edit_message_text(f"سرویس: {service_label(service)}\nکشور مورد نظر را انتخاب کن:",reply_markup=page_keyboard(items,"cty",page,20))


async def buy_country(q, context, country: str) -> None:
    service=context.user_data.get("selected_service")
    if not service: await q.edit_message_text("فرآیند خرید منقضی شده؛ دوباره از منوی خرید شروع کن."); return
    prices=context.user_data.get("price_cache",{})
    data=prices.get(country,{}).get(service,{})
    chosen=choose_operator(data,price_rate(bot_key_of(context)))
    if not chosen: await q.edit_message_text("موجودی این کشور تمام شده است."); return
    op,price,count=chosen
    if context.user_data.pop("lookup_only",False):
        lines=[f"کشور: {country_label(country)}",f"سرویس: {service_label(service)}","قیمت و موجودی اپراتورها:"]
        for op_name,details in data.items():
            if isinstance(details,dict) and float(details.get("cost") or 0)>0:
                try: lines.append(f"{op_name}: {money(math.ceil(float(details['cost'])*price_rate(bot_key_of(context))))} تومان | {int(details.get('count') or 0)} عدد")
                except Exception: pass
        await q.edit_message_text("\n".join(lines)); return
    base_cost=float(data.get(op,{}).get("cost",0) or 0)
    base_price=math.ceil(base_cost*price_rate("main"))
    context.user_data["pending_number"]={"service":service,"country":country,"operator":op,"price":price,"base_price":base_price}
    kb=InlineKeyboardMarkup([[InlineKeyboardButton("✅ تأیید و خرید",callback_data="numberconfirm"),InlineKeyboardButton("❌ انصراف",callback_data="close")]])
    await q.edit_message_text(f"مشخصات خرید:\n\nسرویس: {service_label(service)}\nکشور: {country_label(country)}\nقیمت: {money(price)} تومان\nموجودی: {count}\n\nخرید انجام شود؟",reply_markup=kb)


async def purchase_number(q, context, bot_key: str) -> None:
    uid=q.from_user.id; pending=context.user_data.get("pending_number")
    if not pending: await q.edit_message_text("اطلاعات خرید پیدا نشد؛ دوباره شروع کن."); return
    row=get_user(bot_key,uid)
    if not row: await q.edit_message_text("کاربر پیدا نشد."); return
    if (setting("sales_active","1",bot_key)!="1" or (bot_key!="main" and setting("reseller_sales_active","0")!="1")) and not is_admin(uid,bot_key):
        await q.edit_message_text("فروش شماره فعلاً متوقف است."); return
    price=float(pending["price"])
    with db_connect() as c:
        c.execute("BEGIN IMMEDIATE")
        r=c.execute("SELECT balance,active_order,step FROM users WHERE bot_key=? AND user_id=?",(bot_key,uid)).fetchone()
        if not r:
            c.rollback(); await q.edit_message_text("حساب کاربری پیدا نشد."); return
        if r["active_order"] or r["step"] in ("getting_number","waiting_sms"):
            c.rollback(); await q.edit_message_text("یک شماره فعال داری؛ اول کد آن را دریافت یا شماره را لغو کن."); return
        if float(r["balance"])<price:
            c.rollback(); await q.edit_message_text(f"موجودی کافی نیست.\nقیمت: {money(price)} تومان\nموجودی: {money(float(r['balance']))} تومان\nاز منوی شارژ حساب اقدام کن."); return
        base_price=float(pending.get("base_price",price))
        if bot_key!="main":
            reseller=c.execute("SELECT bot_type,panel_balance FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
            if reseller and reseller["bot_type"]=="gold":
                if float(reseller["panel_balance"] or 0)<base_price:
                    c.rollback(); await q.edit_message_text(f"موجودی پنل ربات طلایی کافی نیست.\nموجودی پنل: {money(float(reseller['panel_balance'] or 0))} تومان\nهزینه پایه این شماره: {money(base_price)} تومان\nمدیر ربات باید پنل را شارژ کند."); return
                c.execute("UPDATE reseller_bots SET panel_balance=panel_balance-? WHERE bot_username=?",(base_price,bot_key.split(":",1)[-1]))
        c.execute("UPDATE users SET balance=balance-?,step='getting_number',service=?,country=?,country_name=?,operator=?,active_price=? WHERE bot_key=? AND user_id=?",(price,pending['service'],pending['country'],country_label(pending['country']),pending['operator'],price,bot_key,uid))
        c.commit()
    await q.edit_message_text("در حال دریافت شماره از پنل…")
    try: raw=await five_sim("getNumber",service=pending["service"],operator=pending["operator"],country=pending["country"])
    except Exception as e:
        await refund(bot_key,uid,price,"number_api_error",float(pending.get("base_price",price)))
        update_user(bot_key,uid,step="none",active_price=0)
        await q.edit_message_text(f"خطا در اتصال به پنل؛ مبلغ به کیف پول برگشت خورد.\n{e}"); return
    parts=raw.split(":")
    if len(parts)<3 or parts[0]!="ACCESS_NUMBER":
        await refund(bot_key,uid,price,"number_unavailable",float(pending.get("base_price",price)))
        update_user(bot_key,uid,step="none",active_price=0)
        await q.edit_message_text(f"شماره دریافت نشد؛ مبلغ به کیف پول برگشت خورد.\nپاسخ پنل: {raw[:200]}"); return
    provider_id,phone=parts[1],parts[2]
    ts=int(time.time())
    with db_connect() as c:
        c.execute("INSERT INTO orders(bot_key,user_id,provider_id,service,country,country_name,phone,price,base_price,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",(bot_key,uid,provider_id,pending['service'],pending['country'],country_label(pending['country']),phone,price,float(pending.get("base_price",price)),"waiting_sms",ts,ts))
        c.execute("UPDATE users SET active_order=?,active_number=?,step='waiting_sms' WHERE bot_key=? AND user_id=?",(provider_id,phone,bot_key,uid))
    await q.edit_message_text(f"✅ شماره با موفقیت دریافت شد.\n\nسرویس: {service_label(pending['service'])}\nکشور: {country_label(pending['country'])}\nشماره: +{phone}\n\nشماره را در برنامه موردنظر وارد کن. کد پیامکی به‌صورت خودکار همین‌جا ارسال می‌شود.\n\n⏳ مهلت دریافت: ۷ دقیقه",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ لغو شماره",callback_data="cancelnumber")]]))
    context.application.create_task(poll_sms(context.application,bot_key,uid,provider_id,phone,pending['service'],price))
    context.user_data.pop("pending_number",None)


async def refund(bot_key: str, uid: int, amount: float, reason: str, base_price: float=0) -> None:
    with db_connect() as c:
        c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(amount,bot_key,uid))
        c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(bot_key,uid,amount,"refund","success",f"refund-{secrets.token_hex(8)}",int(time.time()),reason))
        if bot_key!="main" and base_price>0:
            c.execute("UPDATE reseller_bots SET panel_balance=panel_balance+? WHERE bot_username=? AND bot_type='gold'",(base_price,bot_key.split(":",1)[-1]))


async def poll_sms(app: Application, bot_key: str, uid: int, provider_id: str, phone: str, service: str, price: float) -> None:
    started=time.monotonic(); bot=app.bot
    while time.monotonic()-started<SMS_TIMEOUT:
        with db_connect() as c: current=c.execute("SELECT status FROM orders WHERE provider_id=? AND bot_key=?",(provider_id,bot_key)).fetchone()
        if not current or current["status"]!="waiting_sms": return
        try:
            status=await five_sim("getStatus",id=provider_id)
        except Exception as e:
            log.warning("SMS polling error for %s: %s",provider_id,e); await asyncio.sleep(POLL_SECONDS); continue
        if status.startswith("STATUS_OK:"):
            code=status.split(":",1)[1]
            with db_connect() as c:
                c.execute("UPDATE orders SET status='completed',sms_code=?,updated_at=? WHERE provider_id=?",(code,int(time.time()),provider_id))
                c.execute("UPDATE users SET step='none',active_order='',active_number='',active_price=0,purchases=purchases+1,purchase_history=substr(coalesce(purchase_history,'') || ?,1,5000) WHERE bot_key=? AND user_id=?",(f"\n+{phone} | {service} | {money(price)} | {now_text()}",bot_key,uid))
            try: await bot.send_message(uid,f"✅ کد پیامکی دریافت شد\n\nشماره: +{phone}\nسرویس: {service_label(service)}\nکد ورود: <code>{code}</code>",parse_mode=ParseMode.HTML,reply_markup=main_keyboard())
            except Exception: pass
            if bot_key!="main":
                with db_connect() as c:
                    order=c.execute("SELECT base_price FROM orders WHERE provider_id=? AND bot_key=?",(provider_id,bot_key)).fetchone()
                    reseller=c.execute("SELECT bot_username,owner_id FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
                    if order and reseller:
                        margin=max(0.0,float(price)-float(order["base_price"] or 0))
                        c.execute("UPDATE reseller_bots SET earnings=earnings+?,sales_total=sales_total+?,order_count=order_count+1 WHERE bot_username=?",(margin,price,reseller["bot_username"]))
                if reseller and margin>0:
                    try: await bot.send_message(reseller["owner_id"],f"💰 فروش موفق در ربات نمایندگی شما؛ سود این سفارش: {money(margin)} تومان")
                    except Exception: pass
            try: await five_sim("setStatus",status="6",id=provider_id)
            except Exception: pass
            await report_sale(bot,uid,phone,service,price,bot_key)
            return
        if status in ("STATUS_CANCEL","NO_ACTIVATION","ACCESS_CANCEL") or status.startswith("STATUS_CANCEL"):
            break
        await asyncio.sleep(POLL_SECONDS)
    try: cancel=await five_sim("setStatus",status="-1",id=provider_id)
    except Exception: cancel="ERROR"
    if cancel.startswith("ACCESS_CANCEL"):
        with db_connect() as c: order=c.execute("SELECT base_price FROM orders WHERE provider_id=? AND bot_key=?",(provider_id,bot_key)).fetchone()
        await refund(bot_key,uid,price,"sms_timeout_cancel",float(order["base_price"] if order else 0))
        with db_connect() as c:
            c.execute("UPDATE orders SET status='cancelled',updated_at=? WHERE provider_id=?",(int(time.time()),provider_id))
            c.execute("UPDATE users SET step='none',active_order='',active_number='',active_price=0 WHERE bot_key=? AND user_id=?",(bot_key,uid))
        try: await bot.send_message(uid,"⌛️ کدی دریافت نشد و شماره لغو شد؛ مبلغ به کیف پولت برگشت خورد.",reply_markup=main_keyboard())
        except Exception: pass
    else:
        try: await bot.send_message(uid,"مهلت دریافت کد تمام شد، اما پنل لغو شماره را تأیید نکرد. برای بررسی با پشتیبانی تماس بگیر.")
        except Exception: pass


async def report_sale(bot,uid,phone,service,price,bot_key):
    target=setting("report_channel",REPORT_CHANNEL,bot_key)
    if not target: return
    masked=phone[:7]+"***" if len(phone)>7 else "***"
    try: await bot.send_message(target,f"✅ شماره مجازی فروخته شد\nشماره: {masked}\nسرویس: {service_label(service)}\nمبلغ: {money(price)} تومان\nکاربر: {uid}\nربات: {bot_key}")
    except Exception as e: log.warning("report failed: %s",e)


async def cancel_number(q, context, bot_key):
    uid=q.from_user.id; row=get_user(bot_key,uid)
    if not row or not row["active_order"]: await q.edit_message_text("شماره فعالی برای لغو وجود ندارد."); return
    oid=row["active_order"]; price=float(row["active_price"] or 0)
    try: status=await five_sim("getStatus",id=oid)
    except Exception as e: await q.edit_message_text(f"خطا در بررسی وضعیت شماره: {e}"); return
    if status.startswith("STATUS_OK:"):
        code=status.split(":",1)[1]
        with db_connect() as c:
            c.execute("UPDATE orders SET status='completed',sms_code=?,updated_at=? WHERE provider_id=?",(code,int(time.time()),oid))
            c.execute("UPDATE users SET step='none',active_order='',active_number='',active_price=0,purchases=purchases+1 WHERE bot_key=? AND user_id=?",(bot_key,uid))
        try: await five_sim("setStatus",status="6",id=oid)
        except Exception: pass
        try: await q.edit_message_text(f"کد قبلاً دریافت شده است: {code}")
        except Exception: pass
        await report_sale(context.bot,uid,row["active_number"],row["service"],price,bot_key)
        return
    try: result=await five_sim("setStatus",status="-1",id=oid)
    except Exception as e: await q.edit_message_text(f"لغو شماره ناموفق بود: {e}"); return
    if result.startswith("ACCESS_CANCEL"):
        with db_connect() as c: order=c.execute("SELECT base_price FROM orders WHERE provider_id=? AND bot_key=?",(oid,bot_key)).fetchone()
        await refund(bot_key,uid,price,"user_cancel",float(order["base_price"] if order else 0))
        with db_connect() as c: c.execute("UPDATE orders SET status='cancelled',updated_at=? WHERE provider_id=?",(int(time.time()),oid))
        update_user(bot_key,uid,step="none",active_order="",active_number="",active_price=0)
        await q.edit_message_text("✅ شماره لغو شد و مبلغ به کیف پول برگشت خورد.",reply_markup=None)
    else: await q.edit_message_text("❌ لغو شماره توسط پنل تأیید نشد؛ مبلغ کسرشده باقی می‌ماند.")


async def account_text(update,bot_key):
    u=update.effective_user; r=get_user(bot_key,u.id)
    await update.effective_message.reply_text(f"👤 اطلاعات حساب\n\nشناسه: {u.id}\nموجودی: {money(float(r['balance']))} تومان\nتعداد زیرمجموعه: {r['referrals']}\nتعداد خرید موفق: {r['purchases']}",reply_markup=main_keyboard())


async def my_orders(update,bot_key):
    uid=update.effective_user.id
    with db_connect() as c: rows=c.execute("SELECT * FROM orders WHERE bot_key=? AND user_id=? ORDER BY id DESC LIMIT 10",(bot_key,uid)).fetchall()
    if not rows: await update.effective_message.reply_text("هنوز خریدی ثبت نکردی.",reply_markup=main_keyboard()); return
    lines=["🛍 آخرین خریدهای شما:"]
    for r in rows: lines.append(f"#{r['id']} | {service_label(r['service'] or '')} | +{r['phone'] or '—'} | {money(float(r['price']))} تومان | {r['status']}")
    await update.effective_message.reply_text("\n".join(lines),reply_markup=main_keyboard())


async def referral_text(update,bot_key,context):
    me=await context.bot.get_me(); r=get_user(bot_key,update.effective_user.id)
    link=f"https://t.me/{me.username}?start={update.effective_user.id}"
    await update.effective_message.reply_text(f"👥 لینک دعوت اختصاصی شما:\n{link}\n\nتعداد زیرمجموعه‌ها: {r['referrals']}\nپورسانت شارژ کیف پول زیرمجموعه‌ها: {setting('referral_percent','10',bot_key)}٪\nپاداش عضویت در کانال: {money(float(setting('referral_join_reward','50',bot_key)))} تومان",reply_markup=main_keyboard())


async def deposit_text(update,bot_key,context):
    update_user(bot_key,update.effective_user.id,step="deposit_amount")
    await update.effective_message.reply_text("مبلغ مورد نظر برای افزایش موجودی را به تومان بفرست (از ۳٬۰۰۰ تا ۱۰۰٬۰۰۰ تومان).",reply_markup=ReplyKeyboardMarkup([["🔙 برگشت"]],resize_keyboard=True))


async def create_deposit(update,bot_key,amount:int,context):
    if amount<3000 or amount>100000: await update.effective_message.reply_text("مبلغ باید بین ۳٬۰۰۰ تا ۱۰۰٬۰۰۰ تومان باشد."); return
    if not PAYMENT_MERCHANT_ID or not PUBLIC_BASE_URL:
        await update.effective_message.reply_text("درگاه پرداخت هنوز تنظیم نشده است. مدیر باید ZARINPAL_MERCHANT_ID و PUBLIC_BASE_URL را در تنظیمات سرور وارد کند.",reply_markup=main_keyboard()); update_user(bot_key,update.effective_user.id,step="none"); return
    reference=secrets.token_urlsafe(16)
    callback=f"{PUBLIC_BASE_URL}/payment/callback/{reference}"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.post("https://api.zarinpal.com/pg/v4/payment/request.json",json={"merchant_id":PAYMENT_MERCHANT_ID,"amount":amount*10,"currency":"IRR","description":f"Wallet top-up for Telegram user {update.effective_user.id}","callback_url":callback,"metadata":{"mobile":""}})
            response.raise_for_status(); data=response.json().get("data",{})
        authority=data.get("authority")
        if not authority: raise RuntimeError(str(response.json()))
        payload={"authority":authority,"user_id":update.effective_user.id,"bot_key":bot_key}
        with db_connect() as c: c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(bot_key,update.effective_user.id,amount,"deposit","pending",reference,int(time.time()),json.dumps(payload)))
        await update.effective_message.reply_text(f"✅ لینک پرداخت ساخته شد.\nمبلغ: {money(amount)} تومان\n\nبرای پرداخت روی لینک زیر بزن:\nhttps://www.zarinpal.com/pg/StartPay/{authority}",reply_markup=main_keyboard())
    except Exception as e: await update.effective_message.reply_text(f"ساخت لینک پرداخت ناموفق بود: {e}",reply_markup=main_keyboard())
    update_user(bot_key,update.effective_user.id,step="none")


async def sim_menu(update,bot_key):
    kb=ReplyKeyboardMarkup([["📲 خرید شارژ"],["🌐 خرید بسته اینترنت"],["🔙 برگشت"]],resize_keyboard=True)
    await update.effective_message.reply_text("💢 خدمات سیم‌کارت اعتباری\n\nخرید شارژ مستقیم برای همراه اول، ایرانسل و رایتل.",reply_markup=kb)


async def sim_operator(update,bot_key):
    kb=ReplyKeyboardMarkup([["🕹 ایرانسل","🕹 همراه اول"],["🕹 رایتل"],["🔙 برگشت"]],resize_keyboard=True)
    await update.effective_message.reply_text("اپراتور سیم‌کارت را انتخاب کن:",reply_markup=kb)


async def sim_amount(update,bot_key,operator):
    update_user(bot_key,update.effective_user.id,step="sim_method",service=operator)
    await update.effective_message.reply_text("مبلغ شارژ را انتخاب کن:",reply_markup=ReplyKeyboardMarkup([["💵 1,000 تومان","💵 2,000 تومان"],["💵 5,000 تومان","💵 10,000 تومان"],["💵 20,000 تومان"],["🔙 برگشت"]],resize_keyboard=True))


async def sim_method(update,bot_key,amount):
    update_user(bot_key,update.effective_user.id,step="sim_type",sim_amount=amount)
    await update.effective_message.reply_text("روش شارژ را انتخاب کن:",reply_markup=ReplyKeyboardMarkup([["📲 مستقیم","💳 دریافت کد شارژ"],["🔙 برگشت"]],resize_keyboard=True))


async def sim_charge_type(update,bot_key,mode):
    update_user(bot_key,update.effective_user.id,step="sim_mobile",sim_mode=mode)
    await update.effective_message.reply_text("نوع شارژ را انتخاب کن:",reply_markup=ReplyKeyboardMarkup([["🚀 شگفت انگیز","🚁 معمولی"],["🔙 برگشت"]],resize_keyboard=True))


async def sim_ask_mobile(update,bot_key,charge_type):
    update_user(bot_key,update.effective_user.id,step="sim_mobile_number",sim_charge_type=charge_type)
    await update.effective_message.reply_text("شماره سیم‌کارت مقصد را با ۰۹ وارد کن:",reply_markup=ReplyKeyboardMarkup([["🔙 برگشت"]],resize_keyboard=True))


async def sim_mobile(update,bot_key,context):
    mobile=re.sub(r"\D","",update.effective_message.text or "")
    if not re.fullmatch(r"09\d{9}",mobile): await update.effective_message.reply_text("شماره موبایل معتبر نیست؛ نمونه: 09123456789"); return
    row=get_user(bot_key,update.effective_user.id)
    update_user(bot_key,update.effective_user.id,sim_mobile=mobile,step="sim_confirm")
    amount=int(row["sim_amount"] or 0); payable=math.ceil(amount*1.09)
    operator=row["service"]; mode=row["sim_mode"]; charge_type=row["sim_charge_type"]
    op_label={"🕹 ایرانسل":"ایرانسل","🕹 همراه اول":"همراه اول","🕹 رایتل":"رایتل"}.get(operator,operator)
    await update.effective_message.reply_text(f"مشخصات شارژ:\nاپراتور: {op_label}\nروش: {'مستقیم' if mode=='topup' else 'دریافت کد شارژ'}\nنوع: {'شگفت‌انگیز' if charge_type=='amazing' else 'معمولی'}\nمبلغ شارژ: {money(amount)} تومان\nشماره: {mobile}\nمبلغ نهایی با ۹٪ کارمزد: {money(payable)} تومان\n\nتأیید می‌کنی؟",reply_markup=ReplyKeyboardMarkup([["بله میخوام 👍","خیر منصرف شدم 👎"],["🔙 برگشت"]],resize_keyboard=True))


async def process_sim_payment(update,bot_key,context,online=False):
    uid=update.effective_user.id; row=get_user(bot_key,uid)
    amount=int(row["sim_amount"] or 0); payable=math.ceil(amount*1.09)
    mobile=row["sim_mobile"]; operator={"🕹 ایرانسل":"MTN","🕹 همراه اول":"MCI","🕹 رایتل":"RTL"}.get(row["service"],"MTN")
    mode=row["sim_mode"] or "topup"; charge_type=row["sim_charge_type"] or "normal"
    if not INAX_USER or not INAX_PASS:
        await update.effective_message.reply_text("سرویس شارژ آینکس تنظیم نشده است.",reply_markup=main_keyboard()); update_user(bot_key,uid,step="none"); return
    if online:
        await create_sim_payment(update,bot_key,payable,context,{"amount":amount,"mobile":mobile,"operator":operator,"mode":mode,"charge_type":charge_type})
        update_user(bot_key,uid,step="none"); return
    if float(row["balance"])<payable:
        await update.effective_message.reply_text(f"موجودی کافی نیست. مبلغ نهایی: {money(payable)} تومان",reply_markup=main_keyboard()); update_user(bot_key,uid,step="none"); return
    with db_connect() as c: c.execute("UPDATE users SET balance=balance-? WHERE bot_key=? AND user_id=?",(payable,bot_key,uid))
    await perform_inax_recharge(context.bot,bot_key,uid,amount,mobile,operator,mode,charge_type,payable,update.effective_message)
    update_user(bot_key,uid,step="none")


async def perform_inax_recharge(bot,bot_key,uid,amount,mobile,operator,mode,charge_type,payable,message=None):
    method="topup" if mode=="topup" else "pin"
    order_id=f"{uid}{int(time.time())}"
    params={"method":method,"username":INAX_USER,"password":INAX_PASS,"amount":amount,"mobile":mobile,"operator":operator,"charge_type":charge_type,"order_id":order_id,"count":1,"company":"eee"}
    try:
        result=json.loads(await http_get("https://inax.ir/webservice.php",params,35))
        if str(result.get("code"))!="1": raise RuntimeError(str(result.get("msg",result)))
    except Exception as e:
        with db_connect() as c:
            c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(payable,bot_key,uid))
            c.execute("INSERT INTO recharge_orders(bot_key,user_id,operator,mobile,amount,charge_type,status,created_at) VALUES(?,?,?,?,?,?,?,?)",(bot_key,uid,operator,mobile,amount,charge_type,"failed_refunded",int(time.time())))
        try: await bot.send_message(uid,f"❌ خرید شارژ ناموفق بود؛ مبلغ {money(payable)} تومان به کیف پول برگشت خورد.\n{str(e)[:250]}",reply_markup=main_keyboard())
        except Exception: pass
        return False
    ref=result.get("ref_code","")
    if mode=="topup": detail=f"کد پیگیری: {ref}"
    else:
        buy=result.get("buy_info",[]); first=buy[0] if isinstance(buy,list) and buy else {}
        detail=f"کد شارژ: {first.get('pin','—')}\nسریال: {first.get('serial','—')}"
    with db_connect() as c: c.execute("INSERT INTO recharge_orders(bot_key,user_id,operator,mobile,amount,charge_type,provider_ref,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(bot_key,uid,operator,mobile,amount,charge_type,str(ref),"success",int(time.time())))
    try: await bot.send_message(uid,f"✅ خرید شارژ موفق بود.\nشماره: {mobile}\nمبلغ شارژ: {money(amount)} تومان\n{detail}",reply_markup=main_keyboard())
    except Exception: log.exception("Recharge succeeded but notification failed for user %s",uid)
    return True


async def create_sim_payment(update,bot_key,payable,context,details):
    if not PAYMENT_MERCHANT_ID or not PUBLIC_BASE_URL:
        await update.effective_message.reply_text("درگاه پرداخت آنلاین تنظیم نشده است.",reply_markup=main_keyboard()); return
    reference=secrets.token_urlsafe(16); callback=f"{PUBLIC_BASE_URL}/payment/callback/{reference}"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.post("https://api.zarinpal.com/pg/v4/payment/request.json",json={"merchant_id":PAYMENT_MERCHANT_ID,"amount":payable*10,"currency":"IRR","description":f"SIM topup {details['mobile']}","callback_url":callback})
            response.raise_for_status(); obj=response.json(); authority=obj.get("data",{}).get("authority")
        if not authority: raise RuntimeError(str(obj))
        payload={"authority":authority,"kind":"sim_recharge","details":details,"payable":payable}
        with db_connect() as c: c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(bot_key,update.effective_user.id,payable,"sim_recharge","pending",reference,int(time.time()),json.dumps(payload,ensure_ascii=False)))
        await update.effective_message.reply_text(f"لینک پرداخت شارژ سیم‌کارت:\n{money(payable)} تومان\nhttps://www.zarinpal.com/pg/StartPay/{authority}",reply_markup=main_keyboard())
    except Exception as e: await update.effective_message.reply_text(f"ساخت لینک پرداخت ناموفق بود: {e}",reply_markup=main_keyboard())


async def telegram_services(update,bot_key):
    if not SENATOR_KEY: await update.effective_message.reply_text("سرویس ممبر هنوز تنظیم نشده است.",reply_markup=main_keyboard()); return
    try:
        data=json.loads(await http_get("https://senatorozv.com/web/web.php",{"apikey":SENATOR_KEY,"type":"list"}))
        products=data.get("products",{})
        rows=[]
        for pid,p in products.items():
            try: price=(float(p.get("amount",0))+float(setting("member_markup",MEMBER_MARKUP,bot_key)))*1000
            except Exception: price=0
            if price>0: rows.append([InlineKeyboardButton(f"{p.get('name',pid)} | {money(price)} تومان",callback_data=f"memberprod:{pid}")])
        rows.append([InlineKeyboardButton("🛒 سفارشات من",callback_data="memberorders")])
        await update.effective_message.reply_text("خدمات تلگرام را انتخاب کن:",reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e: await update.effective_message.reply_text(f"دریافت خدمات ناموفق بود: {e}",reply_markup=main_keyboard())


async def member_product(q,context,bot_key,pid):
    try:
        data=json.loads(await http_get("https://senatorozv.com/web/web.php",{"apikey":SENATOR_KEY,"type":"list"}))
        p=data.get("products",{}).get(pid)
        if not p: await q.edit_message_text("این سرویس در دسترس نیست."); return
        unit=float(p.get("amount",0))+float(setting("member_markup",MEMBER_MARKUP,bot_key))
        context.user_data["member_pending"]={"id":pid,"name":p.get("name",pid),"unit":unit}
        await q.edit_message_text(f"{p.get('name',pid)}\nقیمت هر ۱۰۰۰ ممبر: {money(unit*1000)} تومان\n\nتعداد و لینک سفارش را در پیام بعدی با این قالب بفرست:\n`تعداد | لینک`\nمثال: `1000 | https://t.me/channel`",parse_mode=ParseMode.MARKDOWN)
        update_user(bot_key,q.from_user.id,step="member_order")
    except Exception as e: await q.edit_message_text(f"خطا: {e}")


async def create_member_order(update,bot_key,context):
    pending=context.user_data.get("member_pending")
    if not pending: update_user(bot_key,update.effective_user.id,step="none"); await update.effective_message.reply_text("سفارش منقضی شده؛ دوباره سرویس را انتخاب کن.",reply_markup=main_keyboard()); return
    parts=(update.effective_message.text or "").split("|",1)
    try: count=int(parts[0].strip()); link=parts[1].strip()
    except Exception: await update.effective_message.reply_text("قالب صحیح: تعداد | لینک"); return
    if count<100 or count>100000 or not re.match(r"https?://",link): await update.effective_message.reply_text("تعداد یا لینک معتبر نیست."); return
    price=math.ceil(count*pending["unit"])
    context.user_data["member_pending_order"]={"count":count,"link":link,"price":price}
    update_user(bot_key,update.effective_user.id,step="member_confirm")
    await update.effective_message.reply_text(f"سفارش ممبر\nخدمت: {pending['name']}\nتعداد: {count}\nلینک: {link}\nمبلغ: {money(price)} تومان\n\nسفارش ثبت شود؟",reply_markup=ReplyKeyboardMarkup([["✅ تأیید سفارش","❌ لغو سفارش"],["🔙 برگشت"]],resize_keyboard=True))


async def submit_member_order(update,bot_key,context):
    pending=context.user_data.get("member_pending"); order=context.user_data.get("member_pending_order")
    if not pending or not order:
        update_user(bot_key,update.effective_user.id,step="none"); await update.effective_message.reply_text("اطلاعات سفارش پیدا نشد.",reply_markup=main_keyboard()); return
    uid=update.effective_user.id; price=float(order["price"]); count=int(order["count"]); link=order["link"]
    row=get_user(bot_key,uid)
    if float(row["balance"])<price: await update.effective_message.reply_text(f"موجودی کافی نیست. مبلغ سفارش: {money(price)} تومان",reply_markup=main_keyboard()); update_user(bot_key,uid,step="none"); return
    with db_connect() as c: c.execute("UPDATE users SET balance=balance-? WHERE bot_key=? AND user_id=?",(price,bot_key,uid))
    try:
        result=json.loads(await http_get("https://senatorozv.com/web/web.php",{"apikey":SENATOR_KEY,"type":"order","id":pending["id"],"count":count,"link":link},30))
        if str(result.get("result","ok")).lower() not in ("ok","success","1"): raise RuntimeError(str(result.get("description",result)))
        provider_id=str(result.get("order",result.get("id",result.get("order_id",""))))
        if not provider_id: raise RuntimeError(str(result))
    except Exception as e:
        with db_connect() as c: c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(price,bot_key,uid))
        await update.effective_message.reply_text(f"ثبت سفارش ناموفق بود؛ مبلغ برگشت خورد.\n{e}",reply_markup=main_keyboard())
        context.user_data.pop("member_pending",None); context.user_data.pop("member_pending_order",None); update_user(bot_key,uid,step="none"); return
    try:
        with db_connect() as c: c.execute("INSERT INTO member_orders(bot_key,user_id,provider_id,product_id,product_name,link,count,price,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",(bot_key,uid,provider_id,pending["id"],pending["name"],link,count,price,"در صف بررسی",int(time.time())))
    except Exception:
        # The provider accepted the order; do not refund an already-submitted purchase.
        log.exception("Member order %s accepted by provider but could not be stored",provider_id)
        await update.effective_message.reply_text(f"سفارش در پنل ثبت شد اما ذخیره محلی با خطا روبه‌رو شد. شناسه پیگیری: {provider_id}\nبا پشتیبانی تماس بگیر.",reply_markup=main_keyboard())
    else:
        await update.effective_message.reply_text(f"✅ سفارش ثبت شد.\nشناسه: {provider_id}\nخدمت: {pending['name']}\nتعداد: {count}\nمبلغ: {money(price)} تومان",reply_markup=main_keyboard())
    context.user_data.pop("member_pending",None); context.user_data.pop("member_pending_order",None); update_user(bot_key,uid,step="none")


async def member_orders(q,bot_key):
    with db_connect() as c: rows=c.execute("SELECT * FROM member_orders WHERE bot_key=? AND user_id=? ORDER BY id DESC LIMIT 10",(bot_key,q.from_user.id)).fetchall()
    if not rows: await q.edit_message_text("سفارشی ثبت نشده است."); return
    text="🛒 سفارش‌های شما:\n\n"+"\n".join(f"#{r['provider_id']} | {r['product_name']} | {r['count']} | {r['status']}" for r in rows)
    await q.edit_message_text(text)


async def create_panel_topup(update,bot_key,amount:int):
    if amount<10000 or amount>100000000:
        await update.effective_message.reply_text("مبلغ باید بین ۱۰٬۰۰۰ تا ۱۰۰٬۰۰۰٬۰۰۰ تومان باشد."); return
    if bot_key=="main" or not PAYMENT_MERCHANT_ID or not PUBLIC_BASE_URL:
        await update.effective_message.reply_text("درگاه پرداخت یا پنل نمایندگی تنظیم نشده است.",reply_markup=main_keyboard()); return
    username=bot_key.split(":",1)[-1]
    with db_connect() as c: reseller=c.execute("SELECT owner_id,bot_type FROM reseller_bots WHERE bot_username=?",(username,)).fetchone()
    if not reseller or reseller["bot_type"]!="gold":
        await update.effective_message.reply_text("این ربات پنل مستقل قابل شارژ ندارد.",reply_markup=reseller_admin_keyboard()); return
    reference=secrets.token_urlsafe(16); callback=f"{PUBLIC_BASE_URL}/payment/callback/{reference}"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.post("https://api.zarinpal.com/pg/v4/payment/request.json",json={"merchant_id":PAYMENT_MERCHANT_ID,"amount":amount*10,"currency":"IRR","description":f"Gold reseller panel top-up {username}","callback_url":callback})
            response.raise_for_status(); obj=response.json(); authority=obj.get("data",{}).get("authority")
        if not authority: raise RuntimeError(str(obj))
        payload={"authority":authority,"bot_username":username}
        with db_connect() as c: c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(bot_key,update.effective_user.id,amount,"panel_topup","pending",reference,int(time.time()),json.dumps(payload)))
        await update.effective_message.reply_text(f"لینک شارژ پنل طلایی ({money(amount)} تومان):\nhttps://www.zarinpal.com/pg/StartPay/{authority}",reply_markup=reseller_admin_keyboard())
    except Exception as e: await update.effective_message.reply_text(f"ساخت لینک پرداخت ناموفق بود: {e}",reply_markup=reseller_admin_keyboard())
    update_user(bot_key,update.effective_user.id,step="none")


async def start_reseller_purchase(update,context,bot_key,bot_type):
    uid=update.effective_user.id
    if bot_key!="main":
        with db_connect() as c: parent=c.execute("SELECT bot_type FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
        if parent and parent["bot_type"]!="gold":
            await update.effective_message.reply_text("ساخت زیرنمایندگی فقط در ربات طلایی فعال است.",reply_markup=main_keyboard()); return
    with db_connect() as c:
        existing=c.execute("SELECT bot_username FROM reseller_bots WHERE owner_id=? AND parent_bot_key=?",(uid,bot_key)).fetchone()
    if existing:
        await update.effective_message.reply_text(f"برای این ربات قبلاً نمایندگی @{existing['bot_username']} ساخته‌ای.",reply_markup=main_keyboard()); return
    with db_connect() as c: paid_rows=c.execute("SELECT payload FROM transactions WHERE bot_key=? AND user_id=? AND kind='reseller_creation' AND status='success' ORDER BY id DESC LIMIT 10",(bot_key,uid)).fetchall()
    for paid_row in paid_rows:
        try: paid_payload=json.loads(paid_row["payload"] or "{}")
        except Exception: paid_payload={}
        if paid_payload.get("bot_type")==bot_type:
            update_user(bot_key,uid,step="sendtoken",reseller_type=bot_type)
            await update.effective_message.reply_text("پرداخت قبلی شما تأیید شده است. حالا توکن BotFather را ارسال کن.",reply_markup=ReplyKeyboardMarkup([["🔙 برگشت"]],resize_keyboard=True)); return
    if setting("reseller_sales_active","0")!="1" and not is_admin(uid,bot_key):
        await update.effective_message.reply_text("ساخت ربات نمایندگی فعلاً توسط مدیریت متوقف شده است.",reply_markup=main_keyboard()); return
    price=int(float(setting("gold_bot_price" if bot_type=="gold" else "silver_bot_price","10000" if bot_type=="gold" else "0",bot_key)))
    if price<=0:
        update_user(bot_key,uid,step="sendtoken",reseller_type=bot_type)
        await update.effective_message.reply_text("توکن رباتی را که از BotFather گرفتی ارسال کن.\n⚠️ توکن را فقط در گفت‌وگوی خصوصی با همین ربات بفرست.",reply_markup=ReplyKeyboardMarkup([["🔙 برگشت"]],resize_keyboard=True)); return
    if not PAYMENT_MERCHANT_ID or not PUBLIC_BASE_URL:
        await update.effective_message.reply_text("برای ساخت این نوع ربات پرداخت آنلاین تنظیم نشده است. با مدیریت تماس بگیر.",reply_markup=main_keyboard()); return
    reference=secrets.token_urlsafe(16); callback=f"{PUBLIC_BASE_URL}/payment/callback/{reference}"
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.post("https://api.zarinpal.com/pg/v4/payment/request.json",json={"merchant_id":PAYMENT_MERCHANT_ID,"amount":price*10,"currency":"IRR","description":f"{bot_type} reseller bot creation for {uid}","callback_url":callback})
            response.raise_for_status(); obj=response.json(); authority=obj.get("data",{}).get("authority")
        if not authority: raise RuntimeError(str(obj))
        payload={"authority":authority,"kind":"reseller_creation","bot_type":bot_type,"parent_bot_key":bot_key}
        with db_connect() as c: c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(bot_key,uid,price,"reseller_creation","pending",reference,int(time.time()),json.dumps(payload,ensure_ascii=False)))
        await update.effective_message.reply_text(f"هزینه ساخت ربات {'طلایی' if bot_type=='gold' else 'نقره‌ای'}: {money(price)} تومان\nپس از پرداخت، توکن ربات از شما دریافت می‌شود.\nhttps://www.zarinpal.com/pg/StartPay/{authority}",reply_markup=main_keyboard())
    except Exception as e: await update.effective_message.reply_text(f"ساخت لینک پرداخت ناموفق بود: {e}",reply_markup=main_keyboard())


async def admin_start(update,context):
    bot_key=bot_key_of(context)
    if not is_admin(update.effective_user.id,bot_key): return
    await update.effective_message.reply_text("🚦 پنل مدیریت",reply_markup=admin_keyboard() if bot_key=="main" else reseller_admin_keyboard())


async def admin_stats(update):
    with db_connect() as c:
        users=c.execute("SELECT COUNT(*) FROM users WHERE bot_key='main'").fetchone()[0]
        orders=c.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0]
        revenue=c.execute("SELECT COALESCE(SUM(price),0) FROM orders WHERE status='completed'").fetchone()[0]
        balances=c.execute("SELECT COALESCE(SUM(balance),0) FROM users WHERE bot_key='main'").fetchone()[0]
    await update.effective_message.reply_text(f"📊 آمار ربات\nکاربران: {users}\nشماره‌های تحویل‌شده: {orders}\nفروش ثبت‌شده: {money(revenue)} تومان\nمجموع کیف پول‌ها: {money(balances)} تومان",reply_markup=admin_keyboard())


async def admin_text(update,context,bot_key):
    if not is_admin(update.effective_user.id,bot_key_of(context)): return False
    t=(update.effective_message.text or "").strip(); uid=update.effective_user.id
    if bot_key != "main":
        if t in ("/panel","پنل"):
            await update.effective_message.reply_text("🚦 پنل مدیریت نمایندگی",reply_markup=reseller_admin_keyboard()); return True
        if t=="📊 آمار ربات من":
            with db_connect() as c:
                users=c.execute("SELECT COUNT(*) FROM users WHERE bot_key=?",(bot_key,)).fetchone()[0]
                orders=c.execute("SELECT COUNT(*) FROM orders WHERE bot_key=? AND status='completed'",(bot_key,)).fetchone()[0]
                total=c.execute("SELECT COALESCE(SUM(price),0) FROM orders WHERE bot_key=? AND status='completed'",(bot_key,)).fetchone()[0]
                reseller=c.execute("SELECT earnings,order_count,panel_balance,bot_type FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
            earnings=float(reseller["earnings"] if reseller else 0); panel=float(reseller["panel_balance"] if reseller else 0)
            bot_type=reseller["bot_type"] if reseller else "silver"
            await update.effective_message.reply_text(f"نوع ربات: {bot_type}\nکاربران: {users}\nشماره‌های تحویل‌شده: {orders}\nفروش: {money(total)} تومان\nسود قابل تسویه: {money(earnings)} تومان\nموجودی پنل: {money(panel)} تومان",reply_markup=reseller_admin_keyboard()); return True
        if t=="💸 درخواست تسفیه":
            with db_connect() as c:
                reseller=c.execute("SELECT owner_id,earnings,bot_username FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
                if not reseller or float(reseller["earnings"])<10000:
                    await update.effective_message.reply_text("حداقل مبلغ درخواست تسویه ۱۰٬۰۰۰ تومان است.",reply_markup=reseller_admin_keyboard()); return True
                pending=c.execute("SELECT 1 FROM payout_requests WHERE bot_username=? AND status='pending'",(reseller["bot_username"],)).fetchone()
                if pending:
                    await update.effective_message.reply_text("یک درخواست تسویه در انتظار بررسی داری.",reply_markup=reseller_admin_keyboard()); return True
                c.execute("INSERT INTO payout_requests(bot_username,owner_id,amount,status,created_at) VALUES(?,?,?,'pending',?)",(reseller["bot_username"],uid,reseller["earnings"],int(time.time())))
                amount=float(reseller["earnings"])
            for admin_id in ADMIN_IDS:
                try: await context.bot.send_message(admin_id,f"درخواست تسویه نمایندگی @{reseller['bot_username']}\nمالک: {uid}\nمبلغ: {money(amount)} تومان\nبرای بررسی از پنل مدیریت اقدام کن.")
                except Exception: pass
            await update.effective_message.reply_text("درخواست تسویه برای مدیریت ارسال شد.",reply_markup=reseller_admin_keyboard()); return True
        if t=="💳 شارژ پنل":
            with db_connect() as c: reseller=c.execute("SELECT bot_type FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
            if not reseller or reseller["bot_type"]!="gold":
                await update.effective_message.reply_text("شارژ پنل مستقل فقط برای ربات طلایی است.",reply_markup=reseller_admin_keyboard()); return True
            update_user(bot_key,uid,step="panel_topup_amount")
            await update.effective_message.reply_text("مبلغ شارژ پنل را به تومان بفرست (حداقل ۱۰٬۰۰۰ تومان):",reply_markup=ReplyKeyboardMarkup([["خروج از پنل"]],resize_keyboard=True)); return True
        if t=="💸 تعیین ضریب قیمت":
            update_user(bot_key,uid,step="reseller_markup"); await update.effective_message.reply_text(f"ضریب قیمت را بفرست؛ حداقل {money(price_rate('main'))} است.",reply_markup=ReplyKeyboardMarkup([["خروج از پنل"]],resize_keyboard=True)); return True
        if t=="📢 تنظیم کانال":
            update_user(bot_key,uid,step="reseller_channel"); await update.effective_message.reply_text("یوزرنیم کانال را بدون @ بفرست:",reply_markup=ReplyKeyboardMarkup([["خروج از پنل"]],resize_keyboard=True)); return True
        if t=="📍 ارسال پیام همگانی":
            update_user(bot_key,uid,step="admin_broadcast"); await update.effective_message.reply_text("پیام همگانی را بفرست:",reply_markup=ReplyKeyboardMarkup([["خروج از پنل"]],resize_keyboard=True)); return True
        if t=="❎ شروع فروش": set_setting("sales_active","1",bot_key); await update.effective_message.reply_text("فروش فعال شد.",reply_markup=reseller_admin_keyboard()); return True
        if t=="⛔️ توقف فروش": set_setting("sales_active","0",bot_key); await update.effective_message.reply_text("فروش متوقف شد.",reply_markup=reseller_admin_keyboard()); return True
        return False
    if t in ("/panel","پنل"):
        await update.effective_message.reply_text("🚦 پنل مدیریت",reply_markup=admin_keyboard()); return True
    if t=="📍 امار ربات": await admin_stats(update); return True
    if t=="⛔️ توقف فروش": set_setting("sales_active","0"); await update.effective_message.reply_text("فروش متوقف شد.",reply_markup=admin_keyboard()); return True
    if t=="❎ شروع فروش": set_setting("sales_active","1"); await update.effective_message.reply_text("فروش فعال شد.",reply_markup=admin_keyboard()); return True
    if t=="⛔️ توقف فروش نمایندگی ها": set_setting("reseller_sales_active","0"); await update.effective_message.reply_text("فروش نمایندگی‌ها متوقف شد.",reply_markup=admin_keyboard()); return True
    if t=="❎ شروع فروش نمایندگی ها": set_setting("reseller_sales_active","1"); await update.effective_message.reply_text("فروش نمایندگی‌ها فعال شد.",reply_markup=admin_keyboard()); return True
    prompts={"💸 تعیین قیمت روبل":("admin_rouble","قیمت هر روبل را به تومان بفرست:"),"💸 تعیین قیمت ممبر":("admin_member_markup","مقدار افزایش قیمت هر ۱۰۰۰ ممبر را بفرست:"),"💸 پورسانت زیر مجموعه گیری 👥":("admin_referral_join","مبلغ پاداش ثابت دعوت هر زیرمجموعه را به تومان بفرست:"),"📢 تنظیم کانال ربات":("admin_channel","یوزرنیم کانال را بدون @ بفرست:"),"📍تعیین مبلغ خرید ربات طلایی":("admin_goldprice","مبلغ ساخت ربات طلایی را به تومان بفرست:"),"💸 تعیین مبلغ ربات نقره‌ای":("admin_silverprice","مبلغ ساخت ربات نقره‌ای را به تومان بفرست:")}
    if t in prompts:
        step,prompt=prompts[t]; update_user(bot_key,uid,step=step); await update.effective_message.reply_text(prompt,reply_markup=ReplyKeyboardMarkup([["برگشت 🔙"]],resize_keyboard=True)); return True
    if t=="📍 شارژ پنل":
        bal="نامشخص"; inax_balance="تنظیم نشده"; senator_balance="تنظیم نشده"
        if FIVESIM_KEY:
            try: bal=await five_sim("getBalance")
            except Exception as e: bal=str(e)
        if INAX_USER and INAX_PASS:
            try:
                inax_obj=json.loads(await http_get("https://inax.ir/webservice.php",{"method":"credit","username":INAX_USER,"password":INAX_PASS}))
                inax_balance=inax_obj.get("credit","نامشخص")
            except Exception as e: inax_balance=str(e)
        if SENATOR_KEY:
            try:
                senator_obj=json.loads(await http_get("https://senatorozv.com/web/web.php",{"apikey":SENATOR_KEY,"type":"amount"}))
                senator_balance=senator_obj.get("amount","نامشخص")
            except Exception as e: senator_balance=str(e)
        await update.effective_message.reply_text(f"موجودی پنل 5sim: {bal}\nموجودی آینکس: {inax_balance}\nموجودی سناتور: {senator_balance}",reply_markup=admin_keyboard()); return True
    if t=="👥 مدیریت کاربران":
        await update.effective_message.reply_text("برای مدیریت کاربر:\n/user شناسه\n/add شناسه مبلغ\n/sub شناسه مبلغ\n/ban شناسه\n/unban شناسه\n\nAPI: /createkey شناسه مبلغ\nافزایش موجودی API: /keyadd کلید مبلغ\nدرخواست‌های تسویه: /payouts\nتأیید تسویه: /payapprove شناسه\nپاسخ پشتیبانی: /reply USER_ID متن\nشارژ پنل نمایندگی: /panelcredit یوزرنیم مبلغ (منفی برای کسر)",reply_markup=admin_keyboard()); return True
    if t=="📍 ارسال پیام":
        update_user(bot_key,uid,step="admin_broadcast"); await update.effective_message.reply_text("متن پیام همگانی را بفرست:",reply_markup=ReplyKeyboardMarkup([["برگشت 🔙"]],resize_keyboard=True)); return True
    if t=="📍 افزایش | کاهش موجودی پنل طلایی":
        update_user(bot_key,uid,step="admin_panelcredit"); await update.effective_message.reply_text("یوزرنیم ربات و مبلغ را بفرست؛ برای کسر مبلغ منفی بنویس. نمونه: mybot 50000"); return True
    if t=="📍 لیست نمایندگی ها":
        with db_connect() as c: rows=c.execute("SELECT owner_id,bot_username,active,earnings,sales_total,order_count FROM reseller_bots ORDER BY created_at DESC").fetchall()
        await update.effective_message.reply_text("نمایندگی‌ها:\n"+("\n".join(f"{r['bot_username']} | مالک {r['owner_id']} | فروش {money(r['sales_total'])} | سود {money(r['earnings'])} | {'فعال' if r['active'] else 'خاموش'}" for r in rows) if rows else "موردی ثبت نشده"),reply_markup=admin_keyboard()); return True
    if t=="🛍 خرید های من": return False
    if t=="💵 پرداختی های ربات":
        with db_connect() as c: rows=c.execute("SELECT * FROM transactions WHERE status='success' ORDER BY id DESC LIMIT 15").fetchall()
        await update.effective_message.reply_text("پرداخت‌های موفق:\n"+("\n".join(f"{r['user_id']} | {money(r['amount'])} | {r['kind']}" for r in rows) if rows else "موردی نیست"),reply_markup=admin_keyboard()); return True
    if t=="🛒 شارژهای فروخته شده":
        with db_connect() as c: rows=c.execute("SELECT * FROM recharge_orders ORDER BY id DESC LIMIT 15").fetchall()
        await update.effective_message.reply_text("آخرین شارژها:\n"+("\n".join(f"{r['mobile']} | {r['amount']} | {r['status']}" for r in rows) if rows else "موردی نیست"),reply_markup=admin_keyboard()); return True
    if t=="☑️ پیگیری سفارش ممبر":
        with db_connect() as c: rows=c.execute("SELECT * FROM member_orders WHERE status NOT IN ('تکمیل شد','مبلغ برگشت داده شد','completed','refunded') ORDER BY id DESC LIMIT 20").fetchall()
        await update.effective_message.reply_text("سفارش‌های در انتظار:\n"+("\n".join(f"#{r['provider_id']} | کاربر {r['user_id']} | {r['count']} | {r['status']}" for r in rows) if rows else "سفارش در انتظاری نیست."),reply_markup=admin_keyboard()); return True
    if t=="💳 پیگیری پرداخت":
        with db_connect() as c: rows=c.execute("SELECT * FROM transactions WHERE status='pending' ORDER BY id DESC LIMIT 20").fetchall()
        await update.effective_message.reply_text("پرداخت‌های در انتظار:\n"+("\n".join(f"#{r['id']} | {r['user_id']} | {money(r['amount'])} | {r['kind']} | {r['reference']}" for r in rows) if rows else "پرداخت در انتظاری نیست."),reply_markup=admin_keyboard()); return True
    return False


async def admin_commands(update,context):
    bot_key=bot_key_of(context)
    if not is_admin(update.effective_user.id,bot_key): return
    cmd=update.effective_message.text.split()
    if not cmd: return
    cmd[0]=cmd[0].split("@",1)[0]
    if cmd[0] in ("/payouts","/payapprove","/createkey","/keyadd","/grantbot","/panelcredit") and update.effective_user.id not in ADMIN_IDS:
        return
    if cmd[0]=="/reply" and len(cmd)>=3:
        try: target_id=int(cmd[1])
        except ValueError: await update.effective_message.reply_text("قالب: /reply USER_ID متن پاسخ"); return
        answer=update.effective_message.text.split(maxsplit=2)[2]
        try:
            await context.bot.send_message(target_id,f"👮🏻 پاسخ پشتیبانی:\n\n{answer}")
            with db_connect() as c:
                ticket=c.execute("SELECT id FROM support_messages WHERE bot_key=? AND user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",(bot_key,target_id)).fetchone()
                if ticket: c.execute("UPDATE support_messages SET answer=?,status='answered',answered_at=? WHERE id=?",(answer,int(time.time()),ticket["id"]))
            await update.effective_message.reply_text("پاسخ برای کاربر ارسال شد.")
        except Exception as e: await update.effective_message.reply_text(f"ارسال پاسخ ناموفق بود: {e}")
        return
    if cmd[0]=="/payouts":
        with db_connect() as c: rows=c.execute("SELECT * FROM payout_requests WHERE status='pending' ORDER BY id DESC LIMIT 20").fetchall()
        await update.effective_message.reply_text("درخواست‌های تسویه:\n"+("\n".join(f"#{r['id']} @{r['bot_username']} | {r['owner_id']} | {money(r['amount'])} تومان" for r in rows) if rows else "درخواستی نیست.")); return
    if cmd[0]=="/payapprove" and len(cmd)>1:
        try: req_id=int(cmd[1])
        except ValueError: await update.effective_message.reply_text("شناسه درخواست نامعتبر است."); return
        with db_connect() as c:
            req=c.execute("SELECT * FROM payout_requests WHERE id=? AND status='pending'",(req_id,)).fetchone()
            if not req: await update.effective_message.reply_text("درخواست پیدا نشد."); return
            c.execute("UPDATE payout_requests SET status='approved' WHERE id=?",(req_id,))
            c.execute("UPDATE reseller_bots SET earnings=MAX(0,earnings-?) WHERE bot_username=?",(req['amount'],req['bot_username']))
        await update.effective_message.reply_text("درخواست تسویه تأیید شد؛ پرداخت بانکی را خارج از ربات انجام بده.")
        try: await context.bot.send_message(req["owner_id"],f"درخواست تسویه شما برای @{req['bot_username']} تأیید شد. مبلغ: {money(req['amount'])} تومان")
        except Exception: pass
        return
    if cmd[0]=="/grantbot" and len(cmd)>=3:
        try: target_id=int(cmd[1])
        except ValueError: await update.effective_message.reply_text("قالب: /grantbot شناسه gold|silver"); return
        bot_type=cmd[2].lower()
        if bot_type not in ("gold","silver"): await update.effective_message.reply_text("نوع باید gold یا silver باشد."); return
        with db_connect() as c:
            c.execute("INSERT OR IGNORE INTO users(bot_key,user_id,created_at) VALUES(?,?,?)",(bot_key,target_id,int(time.time())))
            c.execute("UPDATE users SET step='sendtoken',reseller_type=? WHERE bot_key=? AND user_id=?",(bot_type,bot_key,target_id))
        try: await context.bot.send_message(target_id,"دسترسی ساخت ربات برای شما فعال شد. توکن BotFather را ارسال کن.")
        except Exception: pass
        await update.effective_message.reply_text("دسترسی ساخت ربات فعال شد."); return
    if cmd[0]=="/panelcredit" and len(cmd)>=3:
        try: amount=float(cmd[2])
        except ValueError: await update.effective_message.reply_text("قالب: /panelcredit username amount"); return
        with db_connect() as c: cur=c.execute("UPDATE reseller_bots SET panel_balance=MAX(0,panel_balance+?) WHERE bot_username=? AND bot_type='gold'",(amount,cmd[1].lstrip("@")))
        await update.effective_message.reply_text("موجودی پنل تغییر کرد." if cur.rowcount else "ربات طلایی پیدا نشد."); return
    if cmd[0]=="/keyadd" and len(cmd)>=3:
        try: amount=float(cmd[2])
        except ValueError: await update.effective_message.reply_text("قالب: /keyadd کلید مبلغ"); return
        with db_connect() as c: cur=c.execute("UPDATE api_keys SET balance=balance+? WHERE api_key=?",(amount,cmd[1]))
        await update.effective_message.reply_text("موجودی کلید افزایش یافت." if cur.rowcount else "کلید پیدا نشد."); return
    if len(cmd)<2: await update.effective_message.reply_text("شناسه کاربر را وارد کن."); return
    try: target=int(cmd[1])
    except ValueError: await update.effective_message.reply_text("شناسه نامعتبر است."); return
    if cmd[0]=="/user":
        r=get_user(bot_key,target)
        await update.effective_message.reply_text("کاربر پیدا نشد." if not r else f"شناسه: {target}\nموجودی: {money(r['balance'])}\nخریدها: {r['purchases']}\nزیرمجموعه: {r['referrals']}\nوضعیت: {'مسدود' if r['blocked'] else 'فعال'}"); return
    if cmd[0] in ("/add","/sub") and len(cmd)>=3:
        try: amount=float(cmd[2])
        except ValueError: await update.effective_message.reply_text("مبلغ نامعتبر است."); return
        with db_connect() as c:
            c.execute("INSERT OR IGNORE INTO users(bot_key,user_id,created_at) VALUES(?,?,?)",(bot_key,target,int(time.time())))
            if cmd[0]=="/add": c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(amount,bot_key,target))
            else: c.execute("UPDATE users SET balance=MAX(0,balance-?) WHERE bot_key=? AND user_id=?",(amount,bot_key,target))
        await update.effective_message.reply_text("موجودی کاربر به‌روزرسانی شد."); return
    if cmd[0]=="/createkey" and len(cmd)>=3:
        try: target_id=int(cmd[1]); initial=float(cmd[2])
        except ValueError: await update.effective_message.reply_text("قالب: /createkey شناسه مبلغ"); return
        key=secrets.token_urlsafe(24)
        with db_connect() as c: c.execute("INSERT INTO api_keys(api_key,owner_id,balance,active,created_at) VALUES(?,?,?,1,?)",(key,target_id,initial,int(time.time())))
        await update.effective_message.reply_text(f"کلید API ساخته شد:\n`{key}`\nموجودی: {money(initial)}",parse_mode=ParseMode.MARKDOWN); return
    if cmd[0] in ("/ban","/unban"):
        with db_connect() as c:
            c.execute("INSERT OR IGNORE INTO users(bot_key,user_id,created_at) VALUES(?,?,?)",(bot_key,target,int(time.time())))
            c.execute("UPDATE users SET blocked=? WHERE bot_key=? AND user_id=?",(1 if cmd[0]=="/ban" else 0,bot_key,target))
        await update.effective_message.reply_text("انجام شد.")


async def process_step(update,context,bot_key,row):
    text=(update.effective_message.text or "").strip(); uid=update.effective_user.id; step=row["step"]
    if step=="sim_method":
        digits=re.sub(r"\D","",text)
        if not digits: await update.effective_message.reply_text("مبلغ را از دکمه‌ها انتخاب کن."); return True
        await sim_method(update,bot_key,int(digits)); return True
    if step=="sim_type":
        mode={"📲 مستقیم":"topup","💳 دریافت کد شارژ":"pin"}.get(text)
        if not mode: await update.effective_message.reply_text("یکی از روش‌های نمایش‌داده‌شده را انتخاب کن."); return True
        await sim_charge_type(update,bot_key,mode); return True
    if step=="sim_mobile":
        charge_type={"🚁 معمولی":"normal","🚀 شگفت انگیز":"amazing"}.get(text)
        if not charge_type: await update.effective_message.reply_text("نوع شارژ را انتخاب کن."); return True
        await sim_ask_mobile(update,bot_key,charge_type); return True
    if step=="sim_mobile_number": await sim_mobile(update,bot_key,context); return True
    if step=="sim_confirm":
        if text=="بله میخوام 👍": await update.effective_message.reply_text("روش پرداخت را انتخاب کن:",reply_markup=ReplyKeyboardMarkup([["💰 پرداخت از کیف پول","💳 پرداخت آنلاین"],["🔙 برگشت"]],resize_keyboard=True)); update_user(bot_key,uid,step="sim_payment"); return True
        if text=="خیر منصرف شدم 👎": update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("سفارش لغو شد.",reply_markup=main_keyboard()); return True
        await update.effective_message.reply_text("برای ادامه «بله میخوام 👍» یا برای لغو «خیر منصرف شدم 👎» را بزن."); return True
    if step=="sim_payment":
        if text=="💰 پرداخت از کیف پول": await process_sim_payment(update,bot_key,context,False); return True
        if text=="💳 پرداخت آنلاین": await process_sim_payment(update,bot_key,context,True); update_user(bot_key,uid,step="none"); return True
        await update.effective_message.reply_text("روش پرداخت را انتخاب کن."); return True
    if step=="delete_reseller_confirm":
        if text in ("✅  بله","✅ بله"):
            with db_connect() as c: target=c.execute("SELECT bot_username FROM reseller_bots WHERE owner_id=? AND parent_bot_key=? AND active=1",(uid,bot_key)).fetchone()
            if not target: update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("ربات پیدا نشد.",reply_markup=main_keyboard()); return True
            await delete_reseller_tree(target["bot_username"])
            update_user(bot_key,uid,step="none")
            await update.effective_message.reply_text(f"ربات @{target['bot_username']} و اطلاعاتش حذف شد.",reply_markup=main_keyboard()); return True
        if text=="❌ لغو حذف":
            update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("حذف لغو شد.",reply_markup=main_keyboard()); return True
        await update.effective_message.reply_text("برای ادامه تأیید یا لغو حذف را انتخاب کن."); return True
    if step=="panel_topup_amount":
        amount=re.sub(r"[,٬\s]","",text)
        if not amount.isdigit(): await update.effective_message.reply_text("فقط مبلغ را به عدد بفرست."); return True
        await create_panel_topup(update,bot_key,int(amount)); return True
    if step=="support_message":
        question=text.strip()
        if not question: await update.effective_message.reply_text("متن پیام پشتیبانی خالی است."); return True
        with db_connect() as c:
            cur=c.execute("INSERT INTO support_messages(bot_key,user_id,question,status,created_at) VALUES(?,?,?,'pending',?)",(bot_key,uid,question,int(time.time())))
            ticket_id=cur.lastrowid
        recipients=set(ADMIN_IDS)
        if bot_key!="main":
            with db_connect() as c: owner=c.execute("SELECT owner_id FROM reseller_bots WHERE bot_username=?",(bot_key.split(":",1)[-1],)).fetchone()
            if owner: recipients.add(int(owner["owner_id"]))
        sent=0
        for admin_id in recipients:
            try:
                await context.bot.send_message(admin_id,f"📩 پیام پشتیبانی #{ticket_id}\nربات: {bot_key}\nکاربر: {uid}\nمتن: {question}\n\nپاسخ: /reply {uid} متن پاسخ")
                sent+=1
            except Exception: pass
        update_user(bot_key,uid,step="none")
        if sent: await update.effective_message.reply_text("پیامت برای پشتیبانی ارسال شد. پاسخ از همین ربات برات میاد.",reply_markup=main_keyboard())
        else:
            support=setting("support_username",SUPPORT_USERNAME,bot_key)
            msg=f"در حال حاضر پشتیبان آنلاین نیست. می‌تونی به @{support} پیام بدی." if support else "پیام ثبت شد؛ اما مدیر پشتیبانی در دسترس نیست."
            await update.effective_message.reply_text(msg,reply_markup=main_keyboard())
        return True
    if step=="deposit_amount":
        amount=re.sub(r"[,٬\s]","",text)
        if not amount.isdigit(): await update.effective_message.reply_text("فقط مبلغ را به عدد بفرست."); return True
        await create_deposit(update,bot_key,int(amount),context); return True
    if step=="member_order": await create_member_order(update,bot_key,context); return True
    if step=="member_confirm":
        if text=="✅ تأیید سفارش": await submit_member_order(update,bot_key,context); return True
        if text=="❌ لغو سفارش": context.user_data.pop("member_pending",None); context.user_data.pop("member_pending_order",None); update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("سفارش لغو شد.",reply_markup=main_keyboard()); return True
        await update.effective_message.reply_text("برای ادامه تأیید یا لغو سفارش را انتخاب کن."); return True
    if step=="admin_broadcast" and is_admin(uid,bot_key):
        update_user(bot_key,uid,step="none")
        with db_connect() as c: targets=c.execute("SELECT user_id FROM users WHERE bot_key=? AND blocked=0",(bot_key,)).fetchall()
        ok=0
        for r in targets:
            try: await context.bot.copy_message(r[0],update.effective_chat.id,update.effective_message.message_id); ok+=1
            except Exception: pass
        await update.effective_message.reply_text(f"ارسال تمام شد: {ok} نفر",reply_markup=admin_keyboard() if bot_key=="main" else reseller_admin_keyboard()); return True
    settings_steps={"admin_rouble":"rouble_rate","admin_member_markup":"member_markup","admin_referral_join":"referral_join_reward","admin_channel":"main_channel","admin_goldprice":"gold_bot_price","admin_silverprice":"silver_bot_price"}
    if step in settings_steps and is_admin(uid,bot_key):
        key=settings_steps[step]
        if step=="admin_channel": value=text.lstrip("@").strip()
        else:
            try: value=float(text.replace(",",""))
            except ValueError: await update.effective_message.reply_text("مقدار نامعتبر است؛ دوباره بفرست."); return True
        if step in ("admin_rouble","admin_goldprice","admin_silverprice","admin_referral_join") and value<0:
            await update.effective_message.reply_text("مقدار نمی‌تواند منفی باشد."); return True
        if step=="admin_rouble" and value<1:
            await update.effective_message.reply_text("ضریب روبل باید حداقل ۱ باشد."); return True
        if step=="admin_member_markup" and value<0:
            await update.effective_message.reply_text("افزایش قیمت ممبر نمی‌تواند منفی باشد."); return True
        set_setting(key,value,bot_key); update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("تنظیم ذخیره شد.",reply_markup=admin_keyboard() if bot_key=="main" else reseller_admin_keyboard()); return True
    if step=="admin_panelcredit" and is_admin(uid,bot_key):
        parts=text.split()
        if len(parts)!=2: await update.effective_message.reply_text("قالب: username amount"); return True
        try: amount=float(parts[1])
        except ValueError: await update.effective_message.reply_text("مبلغ نامعتبر است."); return True
        with db_connect() as c:
            cur=c.execute("UPDATE reseller_bots SET panel_balance=MAX(0,panel_balance+?) WHERE bot_username=? AND bot_type='gold'",(amount,parts[0].lstrip("@")))
        update_user(bot_key,uid,step="none")
        await update.effective_message.reply_text("موجودی پنل به‌روزرسانی شد." if cur.rowcount else "ربات طلایی پیدا نشد.",reply_markup=admin_keyboard()); return True
    if step=="reseller_markup" and is_admin(uid,bot_key):
        try: value=float(text.replace(",",""))
        except ValueError: await update.effective_message.reply_text("ضریب نامعتبر است."); return True
        if value<price_rate("main") or value>10000: await update.effective_message.reply_text(f"ضریب باید حداقل {money(price_rate('main'))} و حداکثر ۱۰٬۰۰۰ باشد."); return True
        set_setting("markup",value,bot_key); update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("ضریب ذخیره شد.",reply_markup=reseller_admin_keyboard()); return True
    if step=="reseller_channel" and is_admin(uid,bot_key):
        set_setting("main_channel",text.lstrip("@"),bot_key); update_user(bot_key,uid,step="none"); await update.effective_message.reply_text("کانال ذخیره شد.",reply_markup=reseller_admin_keyboard()); return True
    if step=="sendtoken":
        if update.effective_chat.type!="private":
            await update.effective_message.reply_text("توکن را فقط در گفت‌وگوی خصوصی با ربات بفرست."); return True
        token=text.strip()
        try: await update.effective_message.delete()
        except Exception: pass
        if not re.fullmatch(r"\d{5,}:[A-Za-z0-9_-]{20,}",token): await update.effective_message.reply_text("توکن معتبر نیست؛ توکن کامل BotFather را بفرست."); return True
        if token==BOT_TOKEN:
            await update.effective_message.reply_text("توکن ربات اصلی را نمی‌توان به‌عنوان ربات نمایندگی ثبت کرد."); return True
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response=await client.get(f"https://api.telegram.org/bot{token}/getMe"); response.raise_for_status(); obj=response.json()
            if not obj.get("ok"): raise RuntimeError("Bot API rejected token")
            username=obj["result"]["username"]
            with db_connect() as c:
                exists=c.execute("SELECT 1 FROM reseller_bots WHERE owner_id=? AND parent_bot_key=?",(uid,bot_key)).fetchone()
                token_exists=c.execute("SELECT 1 FROM reseller_bots WHERE token=?",(token,)).fetchone()
                if exists: await update.effective_message.reply_text("برای هر کاربر فقط یک ربات نمایندگی ثبت می‌شود.",reply_markup=main_keyboard()); update_user(bot_key,uid,step="none"); return True
                if token_exists: await update.effective_message.reply_text("این توکن قبلاً ثبت شده است.",reply_markup=main_keyboard()); update_user(bot_key,uid,step="none"); return True
                c.execute("INSERT INTO reseller_bots(token,bot_username,owner_id,active,markup,channel,created_at,bot_type,parent_bot_key) VALUES(?,?,?,1,?,?,?,?,?)",(token,username,uid,DEFAULT_MARKUP,CHANNEL,int(time.time()),get_user(bot_key,uid)["reseller_type"] or "silver",bot_key))
            child_key=f"reseller:{username}"
            set_setting("welcome_text","😄 سلام {name}\n\nبه ربات شماره مجازی نمایندگی خوش آمدید.",child_key)
            set_setting("main_channel",setting("main_channel",CHANNEL,bot_key),child_key)
            set_setting("support_username",setting("support_username",SUPPORT_USERNAME,bot_key),child_key)
            update_user(bot_key,uid,step="none")
            try:
                child=build_app(token,child_key); await child.initialize(); await child.start(); await recover_pending_sms(child); child.create_task(poll_member_orders_forever(child)); await child.updater.start_polling(drop_pending_updates=False,allowed_updates=Update.ALL_TYPES)
                ACTIVE_RESELLERS[token]=child
            except Exception as e:
                with db_connect() as c: c.execute("DELETE FROM reseller_bots WHERE token=?",(token,))
                await update.effective_message.reply_text(f"اجرای ربات فرزند ناموفق بود؛ ثبت آن لغو شد. خطا: {e}",reply_markup=main_keyboard()); return True
            await update.effective_message.reply_text(f"✅ ربات نمایندگی @{username} ساخته و فعال شد.\nبرای مدیریت ربات، داخل خود ربات دستور پنل را بفرست.",reply_markup=main_keyboard()); return True
        except Exception as e: await update.effective_message.reply_text(f"توکن تأیید نشد: {e}"); return True
    return False


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message or not update.effective_user: return
    bot_key=bot_key_of(context); u=update.effective_user
    row=ensure_user(bot_key,u)
    if int(row["blocked"] or 0) and not is_admin(u.id,bot_key):
        await update.effective_message.reply_text("دسترسی شما به ربات مسدود شده است."); return
    text=(update.effective_message.text or "").strip()
    if text in ("🔙 برگشت","خیر منصرف شدم 👎","/cancel"):
        update_user(bot_key,u.id,step="none",service="",country="",operator="",active_price=0,sim_amount=0,sim_mode="",sim_charge_type="",sim_mobile="")
        await update.effective_message.reply_text("به منوی اصلی برگشتی.",reply_markup=main_keyboard()); return
    if text in ("برگشت 🔙","خروج از پنل") and is_admin(u.id,bot_key):
        update_user(bot_key,u.id,step="none")
        await update.effective_message.reply_text("به پنل مدیریت برگشتی.",reply_markup=admin_keyboard() if bot_key=="main" else reseller_admin_keyboard()); return
    if text=="خروج از پنل":
        update_user(bot_key,u.id,step="none")
        await update.effective_message.reply_text("به منوی اصلی برگشتی.",reply_markup=main_keyboard()); return
    if await process_step(update,context,bot_key,row): return
    if is_admin(u.id,bot_key) and await admin_text(update,context,bot_key): return
    if text=="📲 خرید شماره مجازی":
        context.user_data["lookup_only"]=False
        if not await check_join(update,context): return
        if setting("sales_active","1",bot_key)!="1" and not is_admin(u.id,bot_key): await update.effective_message.reply_text("فروش شماره فعلاً متوقف است.",reply_markup=main_keyboard()); return
        await show_services(update,context); return
    if text in ("✔️ خدمات سیمکارت اعتباری","خدمات سیمکارت اعتباری"):
        await sim_menu(update,bot_key); return
    if text=="📲 خرید شارژ": await sim_operator(update,bot_key); return
    if text in ("🕹 ایرانسل","🕹 همراه اول","🕹 رایتل"): await sim_amount(update,bot_key,text); return
    if text=="🌐 خرید بسته اینترنت": await update.effective_message.reply_text("این بخش در سورس اصلی هم پیام «به‌زودی اضافه می‌شود» داشت.",reply_markup=main_keyboard()); return
    if text=="✔️ خدمات تلگرام": await telegram_services(update,bot_key); return
    if text=="💳 استعلام | قیمت ها":
        if not await check_join(update,context): return
        context.user_data["lookup_only"]=True
        await show_services(update,context); return
    if text=="💸 شارژ حساب": await deposit_text(update,bot_key,context); return
    if text=="👤 اطلاعات حساب": await account_text(update,bot_key); return
    if text=="🛍 خرید های من": await my_orders(update,bot_key); return
    if text=="👥 زیرمجموعه گیری": await referral_text(update,bot_key,context); return
    if text=="🚦 راهنما":
        await update.effective_message.reply_text("با انتخاب سرویس و کشور، قیمت و موجودی از پنل دریافت می‌شود. پس از تأیید خرید، شماره به شما نمایش داده می‌شود و کد پیامکی به‌صورت خودکار ارسال خواهد شد. برای لغو شماره از دکمه لغو استفاده کن.",reply_markup=main_keyboard()); return
    if text=="👮🏻 پشتیبانی":
        update_user(bot_key,u.id,step="support_message")
        await update.effective_message.reply_text("پیام یا مشکل خودت را به‌صورت متنی بفرست تا برای پشتیبانی ارسال شود.",reply_markup=ReplyKeyboardMarkup([["🔙 برگشت"]],resize_keyboard=True)); return
    if text=="💻 پنل فروش":
        with db_connect() as c: reseller=c.execute("SELECT bot_username,earnings,sales_total,order_count,panel_balance,bot_type FROM reseller_bots WHERE owner_id=? AND parent_bot_key=? AND active=1",(u.id,bot_key)).fetchone()
        if not reseller: await update.effective_message.reply_text("هنوز ربات نمایندگی نساختی.",reply_markup=main_keyboard()); return
        await update.effective_message.reply_text(f"💻 پنل فروش نمایندگی @{reseller['bot_username']}\nتعداد سفارش‌های موفق: {reseller['order_count']}\nمجموع فروش: {money(reseller['sales_total'])} تومان\nسود قابل تسویه: {money(reseller['earnings'])} تومان\nموجودی پنل: {money(reseller['panel_balance'])} تومان\nنوع ربات: {reseller['bot_type']}\nبرای تنظیمات داخل ربات نمایندگی دستور پنل را بفرست.",reply_markup=main_keyboard()); return
    if text=="💸 درخواست تسفیه":
        with db_connect() as c:
            reseller=c.execute("SELECT bot_username,earnings FROM reseller_bots WHERE owner_id=? AND parent_bot_key=? AND active=1",(u.id,bot_key)).fetchone()
            if not reseller or float(reseller["earnings"])<10000:
                await update.effective_message.reply_text("حداقل مبلغ درخواست تسویه ۱۰٬۰۰۰ تومان است.",reply_markup=main_keyboard()); return
            pending=c.execute("SELECT 1 FROM payout_requests WHERE bot_username=? AND status='pending'",(reseller["bot_username"],)).fetchone()
            if pending:
                await update.effective_message.reply_text("یک درخواست تسویه در انتظار بررسی داری.",reply_markup=main_keyboard()); return
            amount=float(reseller["earnings"])
            c.execute("INSERT INTO payout_requests(bot_username,owner_id,amount,status,created_at) VALUES(?,?,?,'pending',?)",(reseller["bot_username"],u.id,amount,int(time.time())))
        for admin_id in ADMIN_IDS:
            try: await context.bot.send_message(admin_id,f"درخواست تسویه نمایندگی @{reseller['bot_username']}\nمالک: {u.id}\nمبلغ: {money(amount)} تومان\nدستور بررسی: /payouts")
            except Exception: pass
        await update.effective_message.reply_text("درخواست تسویه برای مدیریت ارسال شد.",reply_markup=main_keyboard()); return
    if text=="🤖 ربات شماره مجازی شما [ربات نمایندگی]":
        with db_connect() as c: existing=c.execute("SELECT bot_username,bot_type FROM reseller_bots WHERE owner_id=? AND parent_bot_key=? AND active=1",(u.id,bot_key)).fetchone()
        if existing:
            await update.effective_message.reply_text(f"ربات نمایندگی شما: @{existing['bot_username']}\nنوع: {existing['bot_type']}\nبرای مدیریت داخل ربات خودتان دستور پنل را بفرست.",reply_markup=ReplyKeyboardMarkup([["💻 پنل فروش"],["❌ حذف ربات من"],["🔙 برگشت"]],resize_keyboard=True))
        else:
            kb=ReplyKeyboardMarkup([["🥇 ساخت ربات"],["🥈 ساخت ربات نقره ای"],["🚦 راهنمای ساخت ربات"],["🔙 برگشت"]],resize_keyboard=True)
            await update.effective_message.reply_text("نوع ربات نمایندگی را انتخاب کن:",reply_markup=kb)
        return
    if text=="❌ حذف ربات من":
        with db_connect() as c: existing=c.execute("SELECT bot_username FROM reseller_bots WHERE owner_id=? AND parent_bot_key=? AND active=1",(u.id,bot_key)).fetchone()
        if not existing: await update.effective_message.reply_text("ربات نمایندگی فعالی برای حذف پیدا نشد.",reply_markup=main_keyboard()); return
        update_user(bot_key,u.id,step="delete_reseller_confirm")
        await update.effective_message.reply_text(f"⚠️ ربات @{existing['bot_username']} و اطلاعات مربوط به آن حذف می‌شود و قابل بازگردانی نیست.\nمطمئنی؟",reply_markup=ReplyKeyboardMarkup([["✅  بله","❌ لغو حذف"],["🔙 برگشت"]],resize_keyboard=True)); return
    if text in ("🥇 ساخت ربات","🥇 ساخت ربات طلایی"): await start_reseller_purchase(update,context,bot_key,"gold"); return
    if text in ("🥈 ساخت ربات نقره ای","🥈 ساخت ربات نقره‌ای","🥈 .ساخت ربات نقره ای"): await start_reseller_purchase(update,context,bot_key,"silver"); return
    if text=="🚦 راهنمای ساخت ربات":
        await update.effective_message.reply_text("برای ساخت ربات، ابتدا نوع طلایی یا نقره‌ای را انتخاب کن. پس از تکمیل پرداخت (در صورت داشتن هزینه)، توکن ربات را از BotFather دریافت و در گفت‌وگوی خصوصی ارسال کن. ربات ساخته‌شده با همان پنل شماره مجازی کار می‌کند.",reply_markup=main_keyboard()); return
    if text=="پنل" and is_admin(u.id): await admin_start(update,context); return
    await update.effective_message.reply_text("متوجه نشدم؛ از دکمه‌های منو استفاده کن.",reply_markup=main_keyboard())


async def on_callback(update: Update,context: ContextTypes.DEFAULT_TYPE) -> None:
    q=update.callback_query
    if not q: return
    await q.answer()
    bot_key=bot_key_of(context); data=q.data or ""
    user_row=get_user(bot_key,q.from_user.id)
    if user_row and int(user_row["blocked"] or 0) and not is_admin(q.from_user.id,bot_key):
        await q.answer("دسترسی شما مسدود است.",show_alert=True); return
    if data=="close": context.user_data.pop("lookup_only",None); await q.edit_message_text("لغو شد."); return
    if data=="joincheck":
        try:
            channel=setting("main_channel",CHANNEL,bot_key_of(context)); m=await context.bot.get_chat_member("@"+channel, q.from_user.id)
            if m.status in ("member","administrator","creator"):
                await award_referral_join(context.bot,bot_key,q.from_user.id)
                await q.edit_message_text("عضویت تأیید شد؛ حالا /start را بزن.")
            else: await q.answer("هنوز عضو کانال نیستی.",show_alert=True)
        except Exception: await q.answer("بررسی عضویت انجام نشد.",show_alert=True)
        return
    if data.startswith("svcpage:"):
        await show_services(update,context,int(data.split(":")[1]),True); return
    if data.startswith("svc:"):
        service=data.split(":",1)[1]; await show_countries(q,context,service); return
    if data.startswith("ctypage:"):
        page=int(data.split(":")[1]); items=context.user_data.get("country_items",[])
        await q.edit_message_text(f"سرویس: {service_label(context.user_data.get('selected_service',''))}\nکشور را انتخاب کن:",reply_markup=page_keyboard(items,"cty",page,20)); return
    if data.startswith("cty:"):
        await buy_country(q,context,data.split(":",1)[1]); return
    if data=="numberconfirm": await purchase_number(q,context,bot_key); return
    if data=="cancelnumber": await cancel_number(q,context,bot_key); return
    if data.startswith("memberprod:"): await member_product(q,context,bot_key,data.split(":",1)[1]); return
    if data=="memberorders": await member_orders(q,bot_key); return


async def post_init(app: Application) -> None:
    init_db()
    me=await app.bot.get_me(); log.info("Bot started: @%s",me.username)
    app.create_task(recover_pending_sms(app))
    app.create_task(poll_member_orders_forever(app))


async def recover_pending_sms(app: Application) -> None:
    await asyncio.sleep(2)
    bot_key=app.bot_data.get("bot_key","main")
    with db_connect() as c: rows=c.execute("SELECT * FROM orders WHERE status='waiting_sms' AND bot_key=?",(bot_key,)).fetchall()
    for r in rows:
        app.create_task(poll_sms(app,r["bot_key"],r["user_id"],r["provider_id"],r["phone"],r["service"],r["price"]))


async def poll_member_orders_forever(app: Application) -> None:
    bot_key=app.bot_data.get("bot_key","main")
    if not SENATOR_KEY: return
    while True:
        try:
            with db_connect() as c: rows=c.execute("SELECT * FROM member_orders WHERE bot_key=? AND status NOT IN ('تکمیل شد','مبلغ برگشت داده شد','completed','refunded') ORDER BY id ASC LIMIT 50",(bot_key,)).fetchall()
            for order in rows:
                try:
                    result=json.loads(await http_get("https://senatorozv.com/web/web.php",{"apikey":SENATOR_KEY,"type":"status","id":order["provider_id"]},20))
                    status=str(result.get("stats",result.get("status","در حال بررسی")))
                    if status==order["status"]: continue
                    with db_connect() as c:
                        c.execute("UPDATE member_orders SET status=? WHERE id=?",(status,order["id"]))
                        if status=="مبلغ برگشت داده شد":
                            c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(order["price"],bot_key,order["user_id"]))
                    if status in ("تکمیل شد","مبلغ برگشت داده شد"):
                        msg=(f"✅ سفارش ممبر شما با شناسه {order['provider_id']} تکمیل شد." if status=="تکمیل شد" else f"❌ سفارش {order['provider_id']} انجام نشد و مبلغ {money(order['price'])} تومان به کیف پول برگشت خورد.")
                    else: msg=f"وضعیت سفارش {order['provider_id']} تغییر کرد: {status}"
                    try: await app.bot.send_message(order["user_id"],msg)
                    except Exception: pass
                except Exception as e: log.warning("member order status failed: %s",e)
        except Exception: log.exception("member order poller failed")
        await asyncio.sleep(60)


def build_app(token: str, bot_key: str="main") -> Application:
    app=Application.builder().token(token).post_init(post_init).build()
    app.bot_data["bot_key"]=bot_key
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("panel",admin_start))
    app.add_handler(CommandHandler(["user","add","sub","ban","unban","payouts","payapprove","createkey","keyadd","grantbot","panelcredit","reply"],admin_commands))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,on_text))
    app.add_handler(MessageHandler(filters.COMMAND,on_text))
    return app


ACTIVE_RESELLERS: dict[str,Application] = {}
web_app=FastAPI(title="Numberino Python API")

@web_app.get("/health")
async def health(): return {"ok":True,"service":"numberino-python"}

@web_app.get("/payment/callback/{reference}")
async def payment_callback(reference: str, Authority: str="", Status: str=""):
    with db_connect() as c: tx=c.execute("SELECT * FROM transactions WHERE reference=? AND kind IN ('deposit','sim_recharge','reseller_creation','panel_topup')",(reference,)).fetchone()
    if not tx: return PlainTextResponse("تراکنش پیدا نشد.",status_code=404)
    if tx["status"]=="success": return HTMLResponse("پرداخت قبلاً ثبت شده است. می‌توانی به تلگرام برگردی.")
    payload=json.loads(tx["payload"] or "{}")
    if Status!="OK" or not Authority or not PAYMENT_MERCHANT_ID: return HTMLResponse("پرداخت انجام نشد یا لغو شد. به تلگرام برگرد.")
    if payload.get("authority") and payload.get("authority")!=Authority:
        return PlainTextResponse("شناسه پرداخت با تراکنش مطابقت ندارد.",status_code=400)
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response=await client.post("https://api.zarinpal.com/pg/v4/payment/verify.json",json={"merchant_id":PAYMENT_MERCHANT_ID,"amount":int(tx["amount"])*10,"authority":Authority})
            response.raise_for_status(); obj=response.json()
        data=obj.get("data",{})
        if int(data.get("code",-1)) not in (100,101): return HTMLResponse(f"تأیید پرداخت ناموفق بود: {data.get('message','خطا')}")
        referral_reward=0.0; inviter_id=0
        referral_pct=float(setting("referral_percent","10",tx["bot_key"])) if tx["kind"]=="deposit" else 0.0
        with db_connect() as c:
            cur=c.execute("UPDATE transactions SET status='success',payload=? WHERE reference=? AND status='pending'",(json.dumps({**payload,"authority":Authority,"verified":data},ensure_ascii=False),reference))
            claimed=cur.rowcount
            if claimed and tx["kind"]=="deposit":
                c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(tx["amount"],tx["bot_key"],tx["user_id"]))
                c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(tx["bot_key"],tx["user_id"],tx["amount"],"deposit_credit","success",f"credit-{reference}",int(time.time()),"zarinpal"))
                buyer=c.execute("SELECT inviter FROM users WHERE bot_key=? AND user_id=?",(tx["bot_key"],tx["user_id"])).fetchone()
                inviter_id=int(buyer["inviter"] or 0) if buyer else 0
                referral_reward=round(float(tx["amount"])*referral_pct/100) if inviter_id else 0.0
                if referral_reward>0:
                    c.execute("UPDATE users SET balance=balance+? WHERE bot_key=? AND user_id=?",(referral_reward,tx["bot_key"],inviter_id))
                    c.execute("INSERT INTO transactions(bot_key,user_id,amount,kind,status,reference,created_at,payload) VALUES(?,?,?,?,?,?,?,?)",(tx["bot_key"],inviter_id,referral_reward,"referral_deposit","success",f"refdep-{reference}",int(time.time()),str(tx["user_id"])))
            if claimed and tx["kind"]=="panel_topup":
                c.execute("UPDATE reseller_bots SET panel_balance=panel_balance+? WHERE bot_username=? AND bot_type='gold'",(tx["amount"],payload.get("bot_username","")))
            if claimed and tx["kind"]=="reseller_creation":
                c.execute("UPDATE users SET step='sendtoken',reseller_type=? WHERE bot_key=? AND user_id=?",(payload.get("bot_type","silver"),tx["bot_key"],tx["user_id"]))
        if not claimed:
            return HTMLResponse("این پرداخت قبلاً پردازش شده است.")
        if tx["kind"]=="deposit":
            bot_token=BOT_TOKEN
            if tx["bot_key"]!="main":
                with db_connect() as c: reseller=c.execute("SELECT token FROM reseller_bots WHERE bot_username=?",(tx["bot_key"].split(":",1)[-1],)).fetchone()
                if reseller: bot_token=reseller["token"]
            try:
                async with Bot(token=bot_token) as payment_bot:
                    await payment_bot.send_message(tx["user_id"],f"✅ پرداخت موفق بود. {money(tx['amount'])} تومان به کیف پول شما اضافه شد.")
                    if inviter_id and referral_reward>0:
                        await payment_bot.send_message(inviter_id,f"🎁 زیرمجموعه شما کیف پولش را شارژ کرد؛ {money(referral_reward)} تومان پورسانت به کیف پول شما اضافه شد.")
            except Exception: log.exception("Could not notify wallet top-up")
        if tx["kind"]=="reseller_creation":
            update_user(tx["bot_key"],tx["user_id"],step="sendtoken",reseller_type=payload.get("bot_type","silver"))
            bot_token=BOT_TOKEN
            if tx["bot_key"]!="main":
                with db_connect() as c: parent=c.execute("SELECT token FROM reseller_bots WHERE bot_username=?",(tx["bot_key"].split(":",1)[-1],)).fetchone()
                if parent: bot_token=parent["token"]
            try:
                async with Bot(token=bot_token) as payment_bot:
                    await payment_bot.send_message(tx["user_id"],"✅ پرداخت ساخت ربات تأیید شد. حالا توکن رباتی را که از BotFather گرفتی در همین گفت‌وگو ارسال کن.")
            except Exception: log.exception("Could not notify reseller creation payment")
            return HTMLResponse("پرداخت تأیید شد. به تلگرام برگرد و توکن ربات را ارسال کن.")
        if tx["kind"]=="panel_topup":
            bot_token=BOT_TOKEN
            if tx["bot_key"]!="main":
                with db_connect() as c: parent=c.execute("SELECT token FROM reseller_bots WHERE bot_username=?",(tx["bot_key"].split(":",1)[-1],)).fetchone()
                if parent: bot_token=parent["token"]
            try:
                async with Bot(token=bot_token) as payment_bot:
                    await payment_bot.send_message(tx["user_id"],f"✅ پنل طلایی شارژ شد. مبلغ: {money(tx['amount'])} تومان")
            except Exception: log.exception("Could not notify panel top-up")
            return HTMLResponse("شارژ پنل تأیید شد. به تلگرام برگرد.")
        if tx["kind"]=="sim_recharge":
            details=payload.get("details",{})
            bot_token=BOT_TOKEN
            if tx["bot_key"]!="main":
                with db_connect() as c: reseller=c.execute("SELECT token FROM reseller_bots WHERE bot_username=?",(tx["bot_key"].split(":",1)[-1],)).fetchone()
                if reseller: bot_token=reseller["token"]
            async with Bot(token=bot_token) as payment_bot:
                await perform_inax_recharge(payment_bot,tx["bot_key"],tx["user_id"],int(details["amount"]),details["mobile"],details["operator"],details["mode"],details["charge_type"],int(payload["payable"]))
            return HTMLResponse("✅ پرداخت و سفارش شارژ ثبت شد. به تلگرام برگرد.")
        return HTMLResponse("✅ پرداخت تأیید شد و موجودی کیف پول به‌روزرسانی شد. به تلگرام برگرد.")
    except Exception as e:
        log.exception("payment verify failed")
        return HTMLResponse(f"خطا در تأیید پرداخت: {str(e)[:200]}",status_code=502)

@web_app.get("/api.php")
async def legacy_api(apikey: str, method: str, country: str="", service: str="", operator: str="any", id: str="", status: str="-1"):
    return await reseller_api(apikey,method,country,service,operator,id,status)

@web_app.get("/api/{api_key}")
async def reseller_api(api_key: str, method: str, country: str="", service: str="", operator: str="any", id: str="", status: str="-1"):
    with db_connect() as c: key=c.execute("SELECT * FROM api_keys WHERE api_key=? AND active=1",(api_key,)).fetchone()
    if not key: return {"result":"error","message":"INVALID_API_KEY"}
    if method=="getBalance": return {"balance":key["balance"]}
    if method=="getStatus":
        with db_connect() as c: r=c.execute("SELECT * FROM api_numbers WHERE provider_id=? AND api_key=?",(id,api_key)).fetchone()
        if not r: return {"result":"error","message":"NO_ACTIVATION"}
        try:
            result=await five_sim("getStatus",id=id)
            with db_connect() as c: c.execute("UPDATE api_numbers SET status=? WHERE provider_id=? AND api_key=?",(result,id,api_key))
            return {"result":result,"number":r["phone"]}
        except Exception as e: return {"result":"error","message":str(e)}
    if method=="setStatus":
        with db_connect() as c: owned=c.execute("SELECT 1 FROM api_numbers WHERE provider_id=? AND api_key=?",(id,api_key)).fetchone()
        if not owned: return {"result":"error","message":"NO_ACTIVATION"}
        try: result=await five_sim("setStatus",status=status,id=id)
        except Exception as e: return {"result":"error","message":str(e)}
        if result.startswith("ACCESS_CANCEL"):
            with db_connect() as c: c.execute("UPDATE api_numbers SET status='cancelled' WHERE provider_id=? AND api_key=?",(id,api_key))
        return {"result":result}
    if method=="getNumber":
        if not country or not service: return {"result":"error","message":"MISSING_PARAMETERS"}
        try:
            prices=await five_prices(country=country,service=service); pdata=prices.get(country,{}).get(service,{})
            options=[(op,v) for op,v in pdata.items() if isinstance(v,dict) and int(v.get("count") or 0)>0 and float(v.get("cost") or 0)>0]
            if not options: return {"result":"error","message":"NO_NUMBERS"}
            if operator!="any": options=[x for x in options if x[0]==operator]
            if not options: return {"result":"error","message":"NO_NUMBERS"}
            op,detail=min(options,key=lambda x:float(x[1].get("cost",999999)))
            charge=math.ceil(float(detail["cost"])*price_rate("main"))
            if float(key["balance"])<charge: return {"result":"error","message":"NO_BALANCE"}
            raw=await five_sim("getNumber",country=country,service=service,operator=op)
            p=raw.split(":")
            if len(p)<3 or p[0]!="ACCESS_NUMBER": return {"result":"error","message":raw}
            provider_id,phone=p[1],p[2]
            with db_connect() as c:
                c.execute("UPDATE api_keys SET balance=balance-? WHERE api_key=?",(charge,api_key))
                c.execute("INSERT INTO api_numbers(provider_id,api_key,phone,status,expires_at) VALUES(?,?,?,'pending',?)",(provider_id,api_key,phone,int(time.time())+600))
            return {"result":"ACCESS_NUMBER","idnumber":provider_id,"number":phone}
        except Exception as e: return {"result":"error","message":str(e)}
    return {"result":"error","message":"UNKNOWN_METHOD"}

async def run_web_server():
    config=uvicorn.Config(web_app,host="0.0.0.0",port=PORT,log_level="warning")
    server=uvicorn.Server(config)
    await server.serve()

async def delete_reseller_tree(bot_username: str) -> None:
    bot_key=f"reseller:{bot_username}"
    with db_connect() as c:
        row=c.execute("SELECT token FROM reseller_bots WHERE bot_username=?",(bot_username,)).fetchone()
        children=c.execute("SELECT bot_username FROM reseller_bots WHERE parent_bot_key=?",(bot_key,)).fetchall()
    for child in children:
        await delete_reseller_tree(child["bot_username"])
    if row:
        token=row["token"]
        child_app=ACTIVE_RESELLERS.pop(token,None)
        if child_app:
            try:
                if child_app.updater: await child_app.updater.stop()
                await child_app.stop(); await child_app.shutdown()
            except Exception: log.exception("Error while stopping reseller bot @%s",bot_username)
    with db_connect() as c:
        c.execute("DELETE FROM orders WHERE bot_key=?",(bot_key,))
        c.execute("DELETE FROM transactions WHERE bot_key=?",(bot_key,))
        c.execute("DELETE FROM member_orders WHERE bot_key=?",(bot_key,))
        c.execute("DELETE FROM recharge_orders WHERE bot_key=?",(bot_key,))
        c.execute("DELETE FROM reseller_settings WHERE bot_key=?",(bot_key,))
        c.execute("DELETE FROM users WHERE bot_key=?",(bot_key,))
        c.execute("DELETE FROM payout_requests WHERE bot_username=?",(bot_username,))
        c.execute("DELETE FROM reseller_bots WHERE bot_username=?",(bot_username,))


async def start_saved_resellers():
    with db_connect() as c: rows=c.execute("SELECT token,bot_username FROM reseller_bots WHERE active=1").fetchall()
    for r in rows:
        token=r["token"]; bot_key=f"reseller:{r['bot_username']}"
        if token==BOT_TOKEN: continue
        try:
            child=build_app(token,bot_key); await child.initialize(); await child.start(); await recover_pending_sms(child); child.create_task(poll_member_orders_forever(child)); await child.updater.start_polling(drop_pending_updates=False,allowed_updates=Update.ALL_TYPES)
            ACTIVE_RESELLERS[token]=child; log.info("Reseller bot started: @%s",r["bot_username"])
        except Exception: log.exception("Could not start reseller bot @%s",r["bot_username"])

async def main() -> None:
    if not BOT_TOKEN: raise SystemExit("BOT_TOKEN is missing. Set it in environment variables.")
    init_db()
    app=build_app(BOT_TOKEN,"main")
    await app.initialize(); await app.start()
    await recover_pending_sms(app)
    app.create_task(poll_member_orders_forever(app))
    if not app.updater: raise RuntimeError("Telegram updater unavailable")
    await app.updater.start_polling(drop_pending_updates=False,allowed_updates=Update.ALL_TYPES)
    await start_saved_resellers()
    web_task=asyncio.create_task(run_web_server())
    log.info("Polling and HTTP API are active")
    try:
        while True: await asyncio.sleep(3600)
    finally:
        web_task.cancel()
        await app.updater.stop(); await app.stop(); await app.shutdown()
        for child in list(ACTIVE_RESELLERS.values()):
            try:
                await child.updater.stop(); await child.stop(); await child.shutdown()
            except Exception: pass

if __name__=="__main__":
    asyncio.run(main())

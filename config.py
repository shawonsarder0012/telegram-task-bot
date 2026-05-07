import os

BOT_TOKEN = os.environ.get("BOT_TOKEN", "8218090305:AACHU7u2w4PzWt2jRzwht70UZm2dM12i4MI")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "5002844213"))
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "nnytt3")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "bee_honey_money_bot")
DATABASE_NAME = "taskbot.db"

REFERRAL_COMMISSION = float(os.environ.get("REFERRAL_COMMISSION", "5"))
REFERRAL_BONUS = float(os.environ.get("REFERRAL_BONUS", "2"))

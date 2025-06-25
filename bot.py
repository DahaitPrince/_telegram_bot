import asyncio
import aiosqlite
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_FILE = "data.db"
pending_credits = {}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, credits INTEGER DEFAULT 0);")
        await db.execute("CREATE TABLE IF NOT EXISTS payments (user_id TEXT, txid TEXT, credits INTEGER, status TEXT, created_at TEXT);")
        await db.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id, credits) VALUES (?, ?);", (user_id, 0))
        await db.commit()
    await update.message.reply_text("👋 Welcome! Use /buy to purchase image credits.")

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "💰 *Buy Image Credits*

"
        "📤 *TRC20 (USDT)* Address:
"
        "`TUmCJ6Q7UWGsiN7Cye6GY9wpLHx7YevyTs`

"
        "💵 *Plans:*
"
        "• ₹100 = 10 images (1.2 USDT)
"
        "• ₹250 = 25 images (3.0 USDT)
"
        "• ₹500 = 60 images (6.0 USDT)

"
        "📌 *After payment*, send the *TXID* (Transaction ID) and plan amount below 👇
"
        "`Example:` TXID: abc123 PLAN: ₹250"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_txid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.message.text.strip()
    if "TXID:" not in message:
        return
    txid = message.split("TXID:")[1].split()[0]
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("INSERT INTO payments (user_id, txid, credits, status, created_at) VALUES (?, ?, ?, ?, ?);",
                         (str(user.id), txid, 0, 'pending', datetime.utcnow().isoformat()))
        await db.commit()
    markup = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{txid}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}_{txid}")
    ]])
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"📥 New payment request
User: @{user.username or user.id}
TXID: `{txid}`", parse_mode="Markdown", reply_markup=markup)
    await update.message.reply_text("✅ TXID submitted. Waiting for admin approval.")

async def handle_payment_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    if query.from_user.id != ADMIN_ID:
        await query.answer("Not authorized", show_alert=True)
        return
    action, user_id, txid = data.split("_", 2)
    if action == "approve":
        pending_credits[query.from_user.id] = {"user_id": user_id, "txid": txid}
        await query.message.reply_text("💬 Please enter number of credits to give:")
        await query.answer()
    elif action == "reject":
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("UPDATE payments SET status='rejected' WHERE txid=?", (txid,))
            await db.commit()
        await context.bot.send_message(chat_id=int(user_id), text="❌ Your payment was rejected.")
        await query.edit_message_text("❌ Payment rejected.")

async def admin_credit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    admin_id = update.effective_user.id
    if admin_id not in pending_credits:
        return
    entry = pending_credits.pop(admin_id)
    user_id = entry["user_id"]
    txid = entry["txid"]
    try:
        credits = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Invalid number. Please enter a valid number.")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE payments SET status='approved', credits=? WHERE txid=?", (credits, txid))
        await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (credits, user_id))
        await db.commit()
    await update.message.reply_text(f"✅ Approved. {credits} credits given to user.")
    await context.bot.send_message(chat_id=int(user_id), text=f"✅ Your payment is approved. You got {credits} credits.")

async def give_credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ You are not authorized.")
        return
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /give <user_id> <credits>")
        return
    try:
        user_id = int(context.args[0])
        credits = int(context.args[1])
    except:
        await update.message.reply_text("❌ Invalid input.")
        return
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute("UPDATE users SET credits = credits + ? WHERE user_id = ?", (credits, user_id))
        await db.commit()
    await update.message.reply_text(f"✅ {credits} credits given to user {user_id}.")
    try:
        await context.bot.send_message(chat_id=user_id, text=f"🎁 You received {credits} free credits from admin!")
    except:
        pass

async def main():
    await init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("buy", buy))
    app.add_handler(CommandHandler("give", give_credits))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_txid))
    app.add_handler(CallbackQueryHandler(handle_payment_action, pattern="^(approve|reject)_"))
    app.add_handler(MessageHandler(filters.User(ADMIN_ID) & filters.TEXT, admin_credit_input))
    print("🤖 Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())

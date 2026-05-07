import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
import sqlite3
import config

# Database Setup
conn = sqlite3.connect(config.DATABASE_NAME, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0.0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS tasks (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    reward REAL NOT NULL,
    proof_type TEXT DEFAULT 'text'
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS submissions (
    submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    task_id INTEGER,
    proof_message TEXT,
    proof_file_id TEXT,
    status TEXT DEFAULT 'pending',
    reviewed_by INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
)
''')
conn.commit()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def is_user_registered(user_id):
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def register_user(user_id, username):
    if not is_user_registered(user_id):
        cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, 0.0)", (user_id, username))
        conn.commit()

def get_user_balance(user_id):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0.0

def get_pending_count():
    cursor.execute("SELECT COUNT(*) FROM submissions WHERE status = 'pending'")
    return cursor.fetchone()[0]

ADD_TASK_TITLE, ADD_TASK_DESC, ADD_TASK_REWARD, ADD_TASK_PROOF_TYPE = range(4)
SUBMIT_SELECT_TASK, SUBMIT_SEND_PROOF = range(2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    username = user.username if user.username else user.full_name
    register_user(user.id, username)

    keyboard = [
        [KeyboardButton("📋 Available Tasks")],
        [KeyboardButton("💰 My Balance"), KeyboardButton("📝 Submit Proof")],
        [KeyboardButton("📞 Support")]
    ]

    if user.id == config.ADMIN_ID:
        keyboard.append([KeyboardButton("🔧 Admin Panel")])

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(f"Welcome {username}! Earn money by completing simple tasks.", reply_markup=reply_markup)

async def available_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT task_id, title, description, reward, proof_type FROM tasks")
    tasks = cursor.fetchall()

    if not tasks:
        await update.message.reply_text("😔 No tasks available right now. Please check back later.")
        return

    text = "📋 *Available Tasks*\n\n"
    keyboard = []
    for task in tasks:
        text += f"*ID: {task[0]}* - {task[1]}\n"
        text += f"Details: {task[2]}\n"
        text += f"Reward: {task[3]} BDT\n"
        text += f"Proof Type: {task[4]}\n\n"
        keyboard.append([InlineKeyboardButton(f"ID: {task[0]} - Submit", callback_data=f"submitstart_{task[0]}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def my_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bal = get_user_balance(user_id)
    await update.message.reply_text(f"💰 Your current balance is: *{bal} BDT*", parse_mode='Markdown')

async def submit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.split('_')[1])
    context.user_data['submit_task_id'] = task_id
    await query.edit_message_text(f"Selected Task ID: {task_id}\n\nPlease send your proof (text, photo, file). Send /cancel to abort.")
    return SUBMIT_SEND_PROOF

async def submit_receive_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    task_id = context.user_data.get('submit_task_id')
    proof_message = update.message.text or update.message.caption or ""
    proof_file_id = None

    if update.message.photo:
        proof_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        proof_file_id = update.message.document.file_id
    elif update.message.video:
        proof_file_id = update.message.video.file_id

    cursor.execute("INSERT INTO submissions (user_id, task_id, proof_message, proof_file_id) VALUES (?, ?, ?, ?)",
                   (user_id, task_id, proof_message, proof_file_id))
    conn.commit()

    await context.bot.send_message(chat_id=config.ADMIN_ID,
                                   text=f"🛎 New Submission\nUser: {update.effective_user.mention_html()}\nTask ID: {task_id}\nMessage: {proof_message}",
                                   parse_mode='HTML')
    await update.message.reply_text("✅ Your proof has been submitted! Wait for admin review.")
    return ConversationHandler.END

async def cancel_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Submission cancelled.")
    return ConversationHandler.END

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return

    pend_count = get_pending_count()
    keyboard = [
        [InlineKeyboardButton("➕ Add New Task", callback_data="admin_addtask")],
        [InlineKeyboardButton(f"📥 Pending Submissions ({pend_count})", callback_data="admin_pending")],
        [InlineKeyboardButton("👥 Users List", callback_data="admin_userslist")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔧 Admin Panel", reply_markup=reply_markup)

async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cursor.execute("SELECT user_id, username, balance FROM users")
    users = cursor.fetchall()
    text = "👥 *Registered Users*\n"
    for u in users:
        text += f"ID: `{u[0]}` - @{u[1]} | Balance: {u[2]} BDT\n"
    await query.edit_message_text(text, parse_mode='Markdown')

async def admin_pending_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cursor.execute("SELECT s.submission_id, s.user_id, u.username, s.task_id, t.title FROM submissions s JOIN users u ON s.user_id = u.user_id JOIN tasks t ON s.task_id = t.task_id WHERE s.status = 'pending'")
    submissions = cursor.fetchall()
    if not submissions:
        await query.edit_message_text("No pending submissions.")
        return

    for sub in submissions:
        sub_id, user_id, username, task_id, task_title = sub
        keyboard = [
            [InlineKeyboardButton("✅ Approve", callback_data=f"approve_{sub_id}_{user_id}_{task_id}"),
             InlineKeyboardButton("❌ Reject", callback_data=f"reject_{sub_id}")],
            [InlineKeyboardButton("View Details", callback_data=f"view_{sub_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(f"🚩 Sub ID: {sub_id}\nUser: @{username}\nTask: {task_title}", reply_markup=reply_markup)
    await query.edit_message_text("Pending list sent below.")

async def admin_view_proof(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub_id = int(query.data.split('_')[1])
    cursor.execute("SELECT proof_message, proof_file_id FROM submissions WHERE submission_id=?", (sub_id,))
    sub = cursor.fetchone()
    if sub:
        text, file_id = sub
        if file_id:
            await context.bot.send_document(chat_id=config.ADMIN_ID, document=file_id, caption=f"Proof Text: {text}")
        else:
            await context.bot.send_message(chat_id=config.ADMIN_ID, text=f"Proof (Text only): {text}")

async def admin_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, sub_id, user_id, task_id = query.data.split('_')
    sub_id, user_id, task_id = int(sub_id), int(user_id), int(task_id)

    cursor.execute("SELECT reward FROM tasks WHERE task_id=?", (task_id,))
    reward = cursor.fetchone()[0]

    cursor.execute("UPDATE submissions SET status='approved', reviewed_by=? WHERE submission_id=?", (config.ADMIN_ID, sub_id))
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))
    conn.commit()

    await context.bot.send_message(chat_id=user_id, text=f"🎉 Your submission {sub_id} approved! You earned {reward} BDT.")
    await query.edit_message_text(f"Approved Sub ID: {sub_id}")

async def admin_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    sub_id = int(query.data.split('_')[1])
    cursor.execute("UPDATE submissions SET status='rejected', reviewed_by=? WHERE submission_id=?", (config.ADMIN_ID, sub_id))
    conn.commit()
    cursor.execute("SELECT user_id FROM submissions WHERE submission_id=?", (sub_id,))
    uid = cursor.fetchone()[0]
    await context.bot.send_message(chat_id=uid, text=f"😞 Your submission {sub_id} was rejected.")
    await query.edit_message_text(f"Rejected Sub ID: {sub_id}")

async def add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.ADMIN_ID:
        return ConversationHandler.END
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("Send Task Title:")
    return ADD_TASK_TITLE

async def add_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Send Task Description:")
    return ADD_TASK_DESC

async def add_task_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['desc'] = update.message.text
    await update.message.reply_text("Send Reward Amount (numeric):")
    return ADD_TASK_REWARD

async def add_task_reward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        reward = float(update.message.text)
        context.user_data['reward'] = reward
    except:
        await update.message.reply_text("Invalid number. Start again.")
        return ConversationHandler.END

    keyboard = [["text", "photo", "file"]]
    await update.message.reply_text("Select proof type:", reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True))
    return ADD_TASK_PROOF_TYPE

async def add_task_proof_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ptype = update.message.text
    if ptype not in ["text", "photo", "file"]:
        ptype = "text"
    cursor.execute("INSERT INTO tasks (title, description, reward, proof_type) VALUES (?, ?, ?, ?)",
                   (context.user_data['title'], context.user_data['desc'], context.user_data['reward'], ptype))
    conn.commit()
    await update.message.reply_text("✅ Task added successfully!")
    return ConversationHandler.END

async def support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Contact admin: @YourUsernameHere")

def main():
    app = Application.builder().token(config.BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^📋 Available Tasks$"), available_tasks))
    app.add_handler(MessageHandler(filters.Regex("^💰 My Balance$"), my_balance))
    app.add_handler(MessageHandler(filters.Regex("^📞 Support$"), support))
    app.add_handler(MessageHandler(filters.Regex("^🔧 Admin Panel$"), admin_panel))

    submission_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(submit_start, pattern="^submitstart_")],
        states={
            SUBMIT_SEND_PROOF: [MessageHandler(filters.TEXT | filters.PHOTO | filters.Document.ALL | filters.VIDEO, submit_receive_proof)]
        },
        fallbacks=[CommandHandler("cancel", cancel_submit)]
    )
    app.add_handler(submission_conv)

    admin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_task_start, pattern="^admin_addtask$")],
        states={
            ADD_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_title)],
            ADD_TASK_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_desc)],
            ADD_TASK_REWARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_reward)],
            ADD_TASK_PROOF_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_proof_type)]
        },
        fallbacks=[]
    )
    app.add_handler(admin_conv)

    app.add_handler(CallbackQueryHandler(admin_users_list, pattern="^admin_userslist$"))
    app.add_handler(CallbackQueryHandler(admin_pending_submissions, pattern="^admin_pending$"))
    app.add_handler(CallbackQueryHandler(admin_view_proof, pattern="^view_"))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(admin_reject, pattern="^reject_"))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
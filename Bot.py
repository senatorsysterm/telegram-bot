import logging
import sqlite3
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, 
    CallbackContext
)
import random

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8446124065:AAG4SGzLajI1a8tcLkV3Yna_qzR9HWun-TY"  # Вставь сюда токен от @BotFather
REFERRAL_REWARD = 50
TASK_REWARD = 25
ADMIN_ID = 1622524932  # Твой Telegram ID

# ==================== База данных ====================
class Database:
    def __init__(self, db_name='bot.db'):
        self.db_name = db_name
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_name)
    
    def init_db(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                stars INTEGER DEFAULT 0,
                referrer_id INTEGER,
                referral_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица истории транзакций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                transaction_type TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица заданий
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_tasks (
                user_id INTEGER,
                task_id INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, task_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def user_exists(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def add_user(self, user_id, username, first_name, referrer_id=None):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, referrer_id)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, referrer_id))
        conn.commit()
        conn.close()
    
    def get_user(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result
    
    def add_stars(self, user_id, amount, trans_type, description):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET stars = stars + ? WHERE user_id = ?
        ''', (amount, user_id))
        cursor.execute('''
            INSERT INTO transactions (user_id, amount, transaction_type, description)
            VALUES (?, ?, ?, ?)
        ''', (user_id, amount, trans_type, description))
        conn.commit()
        conn.close()
    
    def update_referral_count(self, user_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET referral_count = referral_count + 1
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        conn.close()
    
    def get_top_users(self, limit=10):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT user_id, first_name, stars
            FROM users
            ORDER BY stars DESC
            LIMIT ?
        ''', (limit,))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def task_completed(self, user_id, task_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM user_tasks WHERE user_id = ? AND task_id = ?
        ''', (user_id, task_id))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def complete_task(self, user_id, task_id):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO user_tasks (user_id, task_id)
            VALUES (?, ?)
        ''', (user_id, task_id))
        conn.commit()
        conn.close()
    
    def get_history(self, user_id, limit=10):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT amount, transaction_type, description, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit))
        results = cursor.fetchall()
        conn.close()
        return results

# Инициализация БД
db = Database()

# ==================== Меню ====================
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("⭐️ Заработать звёзды", callback_data='earn')],
        [InlineKeyboardButton("👤 Мой профиль", callback_data='profile')],
        [InlineKeyboardButton("📋 Задания", callback_data='tasks')],
        [InlineKeyboardButton("🎰 Рулетка", callback_data='roulette')],
        [InlineKeyboardButton("🏆 Топ пользователей", callback_data='top')],
        [InlineKeyboardButton("📊 История операций", callback_data='history')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== Команда /start ====================
def start(update: Update, context: CallbackContext):
    user = update.effective_user
    referrer_id = None
    
    # Проверяем реферальную ссылку
    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id == user.id:
                referrer_id = None
        except:
            pass
    
    # Добавляем пользователя в БД
    if not db.user_exists(user.id):
        db.add_user(user.id, user.username, user.first_name, referrer_id)
        
        # Начисляем звёзды рефереру
        if referrer_id and db.user_exists(referrer_id):
            db.add_stars(referrer_id, REFERRAL_REWARD, 'referral', 
                        f'Реферал {user.first_name}')
            db.update_referral_count(referrer_id)
            
            # Уведомляем реферера
            try:
                context.bot.send_message(
                    referrer_id,
                    f"🎉 По вашей ссылке зарегистрировался {user.first_name}!\n"
                    f"Вы получили {REFERRAL_REWARD} ⭐️"
                )
            except:
                pass
    
    welcome_text = (
        f"👋 Привет, {user.first_name}!\n\n"
        f"🌟 Добро пожаловать в бот!\n\n"
        f"Здесь ты можешь:\n"
        f"⭐️ Зарабатывать звёзды\n"
        f"👥 Приглашать друзей\n"
        f"🎯 Выполнять задания\n"
        f"🎰 Участвовать в рулетке\n"
        f"🏆 Соревноваться с другими\n\n"
        f"Выбери действие:"
    )
    
    update.message.reply_text(
        welcome_text,
        reply_markup=get_main_menu()
    )

# ==================== Обработка кнопок ====================
def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    
    user_id = query.from_user.id
    
    if query.data == 'earn':
        show_earn_menu(query, user_id, context)
    elif query.data == 'profile':
        show_profile(query, user_id)
    elif query.data == 'tasks':
        show_tasks(query, user_id)
    elif query.data == 'roulette':
        spin_roulette(query, user_id)
    elif query.data == 'top':
        show_top_users(query)
    elif query.data == 'history':
        show_history(query, user_id)
    elif query.data.startswith('complete_task_'):
        task_id = int(query.data.split('_')[-1])
        complete_task(query, user_id, task_id)
    elif query.data == 'back':
        query.edit_message_text(
            "Выбери действие:",
            reply_markup=get_main_menu()
        )

# ==================== Меню "Заработать звёзды" ====================
def show_earn_menu(query, user_id, context):
    bot_username = context.bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    user_data = db.get_user(user_id)
    ref_count = user_data[5] if user_data else 0
    
    text = (
        f"⭐️ **Способы заработка звёзд:**\n\n"
        f"1️⃣ **Пригласи друга** (+{REFERRAL_REWARD} ⭐️)\n"
        f"Твоих рефералов: {ref_count}\n\n"
        f"Твоя реферальная ссылка:\n"
        f"`{ref_link}`\n\n"
        f"2️⃣ **Выполняй задания** (+{TASK_REWARD} ⭐️)\n"
        f"Нажми 📋 Задания\n\n"
        f"3️⃣ **Участвуй в рулетке** 🎰\n"
        f"Испытай удачу!\n"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    
    query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Профиль пользователя ====================
def show_profile(query, user_id):
    user_data = db.get_user(user_id)
    
    if user_data:
        username = f"@{user_data[1]}" if user_data[1] else "Не указан"
        text = (
            f"👤 **Твой профиль**\n\n"
            f"🆔 ID: `{user_data[0]}`\n"
            f"👤 Имя: {user_data[2]}\n"
            f"📱 Username: {username}\n"
            f"⭐️ Звёзд: **{user_data[3]}**\n"
            f"👥 Рефералов: **{user_data[5]}**\n"
            f"📅 Регистрация: {user_data[6][:10]}\n"
        )
    else:
        text = "❌ Профиль не найден"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    
    query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Задания ====================
def show_tasks(query, user_id):
    tasks_list = [
        {"id": 1, "name": "Подписаться на канал", "reward": TASK_REWARD},
        {"id": 2, "name": "Написать отзыв", "reward": TASK_REWARD},
        {"id": 3, "name": "Пригласить 3 друзей", "reward": TASK_REWARD * 2},
        {"id": 4, "name": "Посмотреть видео", "reward": TASK_REWARD},
    ]
    
    text = "📋 **Доступные задания:**\n\n"
    
    keyboard = []
    for task in tasks_list:
        completed = db.task_completed(user_id, task['id'])
        status = "✅" if completed else "🔲"
        text += f"{status} {task['name']} — {task['reward']} ⭐️\n"
        
        if not completed:
            keyboard.append([
                InlineKeyboardButton(
                    f"✅ Выполнить #{task['id']}", 
                    callback_data=f'complete_task_{task["id"]}'
                )
            ])
    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data='back')])
    
    query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Выполнение задания ====================
def complete_task(query, user_id, task_id):
    if db.task_completed(user_id, task_id):
        query.answer("❌ Ты уже выполнил это задание!", show_alert=True)
        return
    
    # Начисляем награду
    reward = TASK_REWARD if task_id != 3 else TASK_REWARD * 2
    db.add_stars(user_id, reward, 'task', f'Задание #{task_id}')
    db.complete_task(user_id, task_id)
    
    query.answer(f"🎉 Задание выполнено! +{reward} ⭐️", show_alert=True)
    show_tasks(query, user_id)

# ==================== Рулетка ====================
def spin_roulette(query, user_id):
    user_data = db.get_user(user_id)
    
    if user_data[3] < 5:
        query.edit_message_text(
            "❌ Недостаточно звёзд!\nНужно минимум 5 ⭐️",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Назад", callback_data='back')
            ]])
        )
        return
    
    # Вычитаем стоимость
    db.add_stars(user_id, -5, 'roulette', 'Участие в рулетке')
    
    # Случайный выигрыш
    prizes = [0, 0, 0, 3, 5, 10, 20, 50, 100]
    prize = random.choice(prizes)
    
    if prize > 0:
        db.add_stars(user_id, prize, 'roulette_win', f'Выигрыш в рулетке')
        result = f"🎉 Поздравляем! Вы выиграли {prize} ⭐️"
    else:
        result = "😔 К сожалению, вы ничего не выиграли"
    
    current_balance = db.get_user(user_id)[3]
    
    keyboard = [
        [InlineKeyboardButton("🎰 Крутить ещё раз", callback_data='roulette')],
        [InlineKeyboardButton("◀️ Назад", callback_data='back')]
    ]
    
    query.edit_message_text(
        f"🎰 **Рулетка**\n\n{result}\n\n"
        f"Твой баланс: {current_balance} ⭐️\n"
        f"Стоимость: 5 ⭐️",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Топ пользователей ====================
def show_top_users(query):
    top = db.get_top_users(10)
    
    text = "🏆 **Топ-10 пользователей:**\n\n"
    
    medals = ["🥇", "🥈", "🥉"]
    
    for i, (user_id, name, stars) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        text += f"{medal} {name} — {stars} ⭐️\n"
    
    if not top:
        text += "Пока нет пользователей"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    
    query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== История операций ====================
def show_history(query, user_id):
    history = db.get_history(user_id, 10)
    
    text = "📊 **Последние операции:**\n\n"
    
    if history:
        for amount, trans_type, description, created_at in history:
            sign = "+" if amount > 0 else ""
            text += f"{sign}{amount} ⭐️ — {description}\n"
            text += f"📅 {created_at[:16]}\n\n"
    else:
        text += "История пуста"
    
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data='back')]]
    
    query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ==================== Главная функция ====================
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    # Регистрация обработчиков
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CallbackQueryHandler(button_handler))
    
    logger.info("Бот запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
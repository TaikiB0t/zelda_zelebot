import os
import psycopg2
import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import random
import time
import json
import urllib.request

# GitHub repo config
GITHUB_USERNAME = "TaikiB0t"
GITHUB_REPO = "zelda_zelebot"
GITHUB_BRANCH = "main"

# Base paths for raw GitHub image access
BASE_CARD_URL = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/mistchypark/"
BASE_STICKER_URL = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/zeldafaces/"

# GitHub API endpoints for folder contents
CARDS_API_URL = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/mistchypark"
STICKERS_API_URL = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/zeldafaces"

# Function to fetch filenames from GitHub folder using API
def get_image_filenames_from_github(api_url):
    try:
        with urllib.request.urlopen(api_url) as response:
            data = json.load(response)
            return [
                item["name"]
                for item in data
                if item["type"] == "file" and item["name"].lower().endswith((".jpg", ".jpeg", ".png", ".webp"))
            ]
    except Exception as e:
        print(f"❌ Failed to load from GitHub API: {e}")
        return []


# ✅ One-time load at startup
card_files = get_image_filenames_from_github(CARDS_API_URL)
sticker_files = get_image_filenames_from_github(STICKERS_API_URL)
print(f"✅ Loaded {len(card_files)} card images")
print(f"✅ Loaded {len(sticker_files)} sticker images")

# Full public URLs to use in bot commands
BRIDGE_OR_PARK_CARDS = [BASE_CARD_URL + filename for filename in card_files]
ZELDA_FACE_STICKERS = [BASE_STICKER_URL + filename for filename in sticker_files]

# Enable logging to debug user tracking
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

TOKEN = os.getenv("BOT_TOKEN")  # Use environment variable for security

# Get PostgreSQL connection URL from Railway environment variables
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("❌ DATABASE_URL is not set! Add it in Railway's environment variables.")

# ✅ List of admin user IDs (replace with actual Telegram user IDs)
# Load from Railway environment
admin_env = os.getenv("BOT_ADMINS", "")
# Parse the comma-separated string into a list of integers
BOT_ADMINS = [int(uid.strip()) for uid in admin_env.split(",") if uid.strip().isdigit()]

# ✅ Replace with your actual Telegram group ID
TARGET_GROUP_ID = os.getenv("TARGET_GROUP_ID")
TEST_GROUP_ID = os.getenv("TEST_GROUP_ID")

# ✅ Store recent messages
recent_messages = []

# ✅ Store the last time the bot triggered #срач
last_dispute_time = 0

# ✅ Time limits (in seconds)
DISPUTE_TIMEOUT = 3600  # 1 hour (3600 seconds)
MESSAGE_WINDOW = 300  # 5 minutes (300 seconds)
MIN_MESSAGES = 20  # Minimum messages in the last 5 minutes

# ✅ List of dispute-triggering phrases (Ukrainian)
DISPUTE_PHRASES = [
    "неправий", "неправа", "не правий", "не права", "непогоджуюсь", "не погоджуюсь",
    "ти не розумієш", "ти не розбираєшся", "це не так", "маячня", "бред", "ну такоє",
    ">>", "незгоден", "не згоден", "мені похуй", "нахуя",
    "незгодна", "не згодна", "так щитаю", "так вважаю", "засуджую", "душніла", "просто похуй",
    "на свій рахунок", "вибач", "мене заділо", "але згодна", "я не люблю"
]

# ✅ Set your chance here (e.g. 30 means 30% chance to react)
RESPONSE_CHANCE_PERCENT = 50

# ✅ All teas in Dzhokonda's menue.
TEAS = {
    # Чорні
    "Вогняне танго": ("Чорні", "Чарівна суміш чорного чаю, кориці та рожевого перцю. Пряний та пікантний смак балансується мʼяким цитрусовим ароматом."),
    "З бергамотом": ("Чорні", "За однією з версій, під час шторму на англійському судні бочки з олією бергамоту перекинулись і зіпсували чай. Проте він прийшовся до смаку."),
    "Золотий равлик": ("Чорні", "Вишуканий чорний чай з провінції Хунань. Винятково молоді чайні тіпси та два наймолодші верхні чайні листи."),
    "Лавандова ніч": ("Чорні", "Мікс чорного чаю що переплітається з пʼянким ароматом квітів лаванди, цедри апельсина та лимона, освіжаючими відтінками листя мʼяти та моринги."),
    "Може гострити": ("Чорні", "Це суміш чорного чаю, цедри апельсина та шматочків імбиру. Відомий як тонізуючий та антиоксидантний напій."),
    "Тандем апельсину та вишні": ("Чорні", "Відбірний цейлонський чай в поєднанні зі шматочками апельсина та вишні, з додаванням пелюстків квітів апельсина та жасмину."),
    "Цейлонський": ("Чорні", "Цейлонський чорний чай найвищого ґатунку. Класичний смак високогірного чаю зі свіжим ароматом."),
    "Чері-чері": ("Чорні", "Справжній подарунок для поціновувачів вишневих насолод: з додаванням шматочків вишні та ароматом вишневої кісточки."),

    # Зелені
    "Зелений равлик": ("Зелені", "Класичний плантаційний чай з провінції Хунань. Виготовлено з молодого листя зеленого чаю, згорнутого по спіралі."),
    "Калейдоскоп.": ("Зелені", "Це гармонійне поєднання ніжного зеленого чаю зі шматочками ананаса, ягодами смородини та пелюстками квітів."),
    "Ліс-Беррі": ("Зелені", "Справжній лісовий смак: цейлонський зелений чай з додаванням кишмишу, листям чорної смородини та ягодами малини, чорниці, журавлини й ожини."),
    "Пан Жасмин": ("Зелені", "Вигатовляють за ритуалом відомим як 'Весілля', під час якого свіжі квіти жасмину змішують з зеленим чаєм, а потім мʼяко запарюють."),
    "Фламінго": ("Зелені", "Як яскраві птахи, він вражає пелюстками сафлору, соняшника та волошки, що доповнені ароматами бергамоту та лимону."),
    "Чайна казка": ("Зелені", "Основа з ніжного зеленого чаю збагачена соковитими шматочками апельсина, папайї та шипшини, а пелюстки гібіскусу додають композиції елегантності."),

    # Травʼяні
    "Бурштинка": ("Травʼяні", "Цей сонячний букет із квітів та ягід тамує спрагу та наповнює організм цілющим теплом..."),
    "Грецький гірський": ("Травʼяні", "Грецький гірський чай вже в давнину цінувався як лікарська рослина. Має свіжий, солодкий аромат з відтінком лимона та кориці..."),
    "Гуаюса": ("Травʼяні", "Це натуральний напій з Еквадору, що поєднує кофеїн та теобромін. Має мʼякий вплив і солодкуватий, горіховий смак."),
    "Імбирний": ("Травʼяні", "Має яскравий смак і теплу пряність імбиру. Цей чай не лише зігріває взимку, але й відомий своїми корисними властивостями."),
    "Кора та корінь": ("Травʼяні", "Глибокий, як древній ліс, та яскравий, як полумʼя. Деревні ноти лапачо та сандалу поєднуються з теплом імбиру на базі ройбушу."),
    "Лабіринт": ("Травʼяні", "Бленд чорного та зеленого чаїв з ягодами шипшини, бузини та чорниці, квітами ромашки, лимоннику та мʼяти, листям ожини."),
    "Медовий куш": ("Травʼяні", "Чай з листя та квітів дикого південноафриканського чагарника ханібушу. Має аромати меду, кориці, груші."),
    "Червоний куш": ("Травʼяні", "Солодкі карамельні нотки південноафриканського ройбоса із додаванням макадамського горіху та білого шоколаду."),
    "Шалена буря": ("Травʼяні", "Суміш ройбоса із яблуком, женьшенем, імбиром, листям омели, чорним перцем та корицею."),

    # Пуери
    "З міста Пуер": ("Пуери", "Хороші речі вимагають часу — повільна ферментація не менше пʼяти років."),
    "Пресований міні-туоча (зелений / чорний)": ("Пуери", "🌚."),
    "Рисовий привид (пресований)": ("Пуери", "Крізь густий деревно-горіховий смак пробивається солодкий шепіт рисових полів. Зігріваючий післясмак."),
    "Таємний Юньнань": ("Пуери", "Шу Пу Ер з пелюстками троянди та полунично-вершковим ароматом дарує нові враження."),
    "Чорний Чжутун (пресований)": ("Пуери", "Відбірний пресований чорний чай у бамбуковому листу. Медово-солодкий смак з легкою вʼязкістю."),

    # Фруктові
    "Джоконда": ("Фруктові", "Запашний букет із квітів та ягід. Терпкий смак літа."),
    "Нахаба": ("Фруктові", "Папайя, яблуко, смородина, гібіскус, шипшина, бузина, родзинки."),
    "Подорож до Тибету": ("Фруктові", "Чорний і зелений чай з ягодами годжі, квітами гранату, жасмином, малиною, порічками."),
    "Таємниця двох світів": ("Фруктові", "Чорний байховий та зелений вʼєтнамський чаї з манго, папайєю, пелюстками соняшника."),
    "Фруктово-мʼятний": ("Фруктові", "Заспокійливий аромат мʼяти з тонким фруктовим присмаком. Апельсинові нотки."),
    "Ягідний етюд": ("Фруктові", "Кишмиш, каркаде, шипшина, обліпиха, родовик, малина, суниця, ожина."),

    # Особливі
    "Білий чай": ("Особливі", "Свіжий подих весняних гір Фуцзяню. Прозорий настій, квітковий аромат, оксамитовий смак."),
    "Гречаний": ("Особливі", "Молоде насіння татарської гречихи. Легкий, вітамінний, нагадує осінь."),
    "Синій чай": ("Особливі", "Анчан. Вишуканий смак, вважається омолоджуючим і допомагає схуднути."),
    "Улун": ("Особливі", "Кремова консистенція, вершковий аромат, солодкуватий присмак. Між чорним і зеленим чаєм."),

    # Літні
    "Квітка пустелі": ("Літні", "Яскраво-червоний настій гібіскуса. Освіжаючий дотик Сходу."),
    "Морозні ягоди.": ("Літні", "Ягоди з памороззю мʼятної свіжості. Арктичний бриз і гармонія."),
    "Ніжний дотик.": ("Літні", "Китайський зелений чай, зібраний у квітні. Весняне пробудження."),
    "Сонячний сад": ("Літні", "Рятівна прохолода. Соковитий, освіжаючий, немов тінистий куточок у саду."),
    "Тропічна прохолода.": ("Літні", "Ананас, манго, апельсин, мандарин, полуниця з сафлором і календулою.")
}
TEA_CATEGORIES = sorted(set(cat for _, (cat, _) in TEAS.items()))


def setup_database():
    """Creates the users table if it doesn't exist"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")  # Force secure connection
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT
            );
        """)
        conn.commit()
        conn.close()
        print("✅ PostgreSQL Database initialized successfully.")
    except Exception as e:
        print(f"❌ Database error: {e}")


def escape_markdown(text: str) -> str:
    """Escapes special characters for Telegram MarkdownV2"""
    if text:
        return re.sub(r'([_*\[\]()~`>#+\-=|{}.!\\])', r'\\\1', text)  # Escape all MarkdownV2 characters
    return ""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command"""
    await update.message.reply_text("мяу")


async def tag_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mentions all stored users except the sender using @username when possible"""
    chat = update.effective_chat
    sender_id = update.message.from_user.id

    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cursor = conn.cursor()

        # Fetch all users from the database
        cursor.execute("SELECT user_id, username, first_name FROM users")
        users = cursor.fetchall()
        conn.close()

        if not users:
            await update.message.reply_text("I don't know anyone in this group yet! Send some messages first.")
            return

        tagged_users = []
        for user_id, username, first_name in users:
            if user_id == sender_id:
                continue
            if username:
                tagged_users.append(f"@{username}")
            else:
                # fallback to tg://user?id=... link if no username
                safe_name = first_name or "user"
                tagged_users.append(f'<a href="tg://user?id={user_id}">{safe_name}</a>')

        if tagged_users:
            message = "няв " + ", ".join(tagged_users)
        else:
            message = "No users found to tag."

        await update.message.reply_text(message, parse_mode="HTML", reply_to_message_id=update.message.message_id)

    except psycopg2.Error as e:
        await update.message.reply_text("❌ Database error. Please check logs.")
        logging.error(f"❌ Database error: {e}")


async def speak(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /speak command but only allows bot admins to use it"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id

    # ✅ Check if the user is an admin
    if user_id not in BOT_ADMINS:
        await update.message.reply_text("няв?")
        return

    if chat_id != user_id:  # Ensure it's a private chat
        await update.message.reply_text("няв?")
        return

    if not context.args:
        await update.message.reply_text("няв?")
        return

    speak_text = " ".join(context.args)  # Extract text after /speak

    try:
        await context.bot.send_message(chat_id=TARGET_GROUP_ID, text=speak_text)
        await update.message.reply_text(f"✅ Sent your message to the group:\n\n🔹 {speak_text}")

        logging.info(f"Admin {user_id} sent message to group {TARGET_GROUP_ID}: {speak_text}")

    except Exception as e:
        logging.error(f"❌ Error sending message to group: {e}")
        await update.message.reply_text("❌ Failed to send the message to the group. Make sure I'm an admin.")


async def spies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates a random 'Spies' matrix when /spies is used"""
    chat_id = update.message.chat_id

    # Randomly decide whether red or blue has 8 agents
    red_count = 8 if random.choice([True, False]) else 7
    blue_count = 15 - red_count  # Total agents = 15 (20 - 4 - 1)

    # Construct the list of tiles
    tiles = (
        ["🟥"] * red_count +
        ["🟦"] * blue_count +
        ["⬜️"] * 4 +
        ["⬛️"]
    )

    # Shuffle the tiles randomly
    random.shuffle(tiles)

    # Format into a 4x5 grid
    grid = ""
    for i in range(0, 20, 5):
        grid += "".join(tiles[i:i+5]) + "\n"

    # Determine who goes first
    first_team = ""
    if red_count == 8:
        first_team = "перші 🟥"
    elif blue_count == 8:
        first_team = "перші 🟦"

    # Send the result
    await update.message.reply_text(grid.strip() + ("\n\n" + first_team if first_team else ""))


async def bridge_or_park(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a random card from Telegram-hosted images with a random number"""
    if not BRIDGE_OR_PARK_CARDS:
        await update.message.reply_text("❌ No cards are available.")
        return

    chosen_card = random.choice(BRIDGE_OR_PARK_CARDS)
    chosen_number = random.randint(1, 3)

    try:
        await update.message.reply_photo(photo=chosen_card, caption=f"🔢 {chosen_number}")
    except Exception as e:
        logging.error(f"❌ Failed to send card: {e}")
        await update.message.reply_text("❌ няв 😿")


async def tea_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(text=cat, callback_data=f"tea_{cat}")]
        for cat in ["Випадковий"] + TEA_CATEGORIES
    ]
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🍵 Який чай бажаєш спробувати?", reply_markup=markup)


async def tea_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected = query.data.replace("tea_", "")
    if selected == "Випадковий":
        tea = random.choice(list(TEAS.keys()))
        category, description = TEAS[tea]
        header = f"🎲 Випадковий вибір: {tea} ({category})"
    else:
        filtered_teas = [name for name, (cat, _) in TEAS.items() if cat == selected]
        tea = random.choice(filtered_teas)
        category, description = TEAS[tea]
        header = f"🍃 Обрано з категорії {category}:\n\n🫖 {tea}"

    await query.edit_message_text(f"{header}\n\n{description}")


async def track_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stores users who send messages in the database and detects @all & polls"""
    global last_dispute_time
    if not update.message:
        return

    user = update.message.from_user
    user_id = user.id
    chat_id = update.message.chat_id  # Group where the message was sent
    username = user.username if user.username else "None"
    first_name = user.first_name if user.first_name else "None"
    text = update.message.text or ""

    logging.info(f"🔹 Received message from: ID={user_id}, Username={username}, First Name={first_name}")

    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        cursor = conn.cursor()

        # Insert or update user info
        cursor.execute("""
            INSERT INTO users (user_id, username, first_name) 
            VALUES (%s, %s, %s) 
            ON CONFLICT(user_id) 
            DO UPDATE SET username=EXCLUDED.username, first_name=EXCLUDED.first_name;
        """, (user_id, username, first_name))

        conn.commit()
        conn.close()
        logging.info(f"✅ User {user_id} stored in the database.")

    except psycopg2.Error as e:
        logging.error(f"❌ Database error: {e}")

    # ✅ Detect messages in the target group and track timestamps
    if chat_id == TARGET_GROUP_ID:
        current_time = time.time()
        recent_messages.append(current_time)

        # ✅ Remove messages older than 5 minutes
        recent_messages[:] = [msg_time for msg_time in recent_messages if current_time - msg_time <= MESSAGE_WINDOW]

        # ✅ Check if dispute detection is active
        if current_time - last_dispute_time > DISPUTE_TIMEOUT:
            # ✅ Condition 1: At least 10 messages in the last 5 minutes
            if len(recent_messages) >= MIN_MESSAGES:
                # ✅ Condition 2: Dispute-related phrases detected
                if any(phrase in text.lower() for phrase in DISPUTE_PHRASES):
                    try:
                        await context.bot.send_message(chat_id=TARGET_GROUP_ID, text="👻 #срач")
                        last_dispute_time = current_time  # Set cooldown
                        logging.info("👻 #срач triggered in the group!")
                    except Exception as e:
                        logging.error(f"❌ Error posting #срач: {e}")

        # ✅ If any user manually posts #срач, disable detection for 1 hour
        if "#срач" in text.lower():
            last_dispute_time = current_time  # Reset cooldown
            logging.info("Dispute detection disabled for 1 hour due to manual #срач.")

    # ✅ Detect if the message contains "@all"
    if "@all" in text.lower():
        await tag_all(update, context)  # Trigger the tagging function

    # ✅ Detect if the message is a poll
    if update.message.poll:
        await update.message.reply_text("🍄 #опитування", reply_to_message_id=update.message.message_id)

    # ✅ Detect specific keywords and send a random sticker
    keywords = [
        "зельда", "зельдос", "Зельда", "Зельдос",
        "зельду", "зельдоса", "Зельду", "Зельдоса",
        "зельдою", "зельдосом", "Зельдою", "Зельдосом"
    ]

    if any(word in text for word in keywords):
        guaranteed = "?" in text

        should_respond = guaranteed or random.randint(1, 100) <= RESPONSE_CHANCE_PERCENT

        if should_respond:
            random_sticker = random.choice(ZELDA_FACE_STICKERS)
            await update.message.reply_sticker(random_sticker, reply_to_message_id=update.message.message_id)
        else:
            logging.info("🎲 Skipped sticker reply due to random chance.")


def main():
    """Start the bot"""
    setup_database()  # Ensure database is set up on start
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler(["tagall", "all"], tag_all))
    app.add_handler(CommandHandler("speak", speak))  # ✅ New CommandHandler for /speak
    app.add_handler(CommandHandler("spies", spies))
    app.add_handler(CommandHandler(["bridge_or_park", "park_or_bridge", "mist_chy_park", "park_chy_mist",
                                    "bridgeorpark", "parkorbridge", "mistchypark", "parkchymist"], bridge_or_park))
    app.add_handler(CommandHandler(["tea", "dzhokonda"], tea_command))
    app.add_handler(CallbackQueryHandler(tea_callback, pattern=r"^tea_"))

    app.add_handler(MessageHandler(filters.ALL, track_users))  # Track users who send messages

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()

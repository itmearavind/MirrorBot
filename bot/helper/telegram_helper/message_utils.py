from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler
from telegram.message import Message
from telegram.update import Update
import psutil, shutil
import time
from bot import dispatcher, AUTO_DELETE_MESSAGE_DURATION, LOGGER, bot, \
    status_reply_dict, status_reply_dict_lock, download_dict, download_dict_lock, botStartTime, Interval, DOWNLOAD_STATUS_UPDATE_INTERVAL, STATUS_LIMIT
from bot.helper.ext_utils.bot_utils import get_readable_message, get_readable_file_size, get_readable_time, MirrorStatus, setInterval
from telegram.error import TimedOut, BadRequest


def sendMessage(text: str, bot, update: Update):
    try:
        return bot.send_message(update.message.chat_id,
                            reply_to_message_id=update.message.message_id,
                            text=text, allow_sending_without_reply=True,  parse_mode='HTMl')
    except Exception as e:
        LOGGER.error(str(e))
def sendMarkup(text: str, bot, update: Update, reply_markup: InlineKeyboardMarkup):
    return bot.send_message(update.message.chat_id,
                            reply_to_message_id=update.message.message_id,
                            text=text, reply_markup=reply_markup, allow_sending_without_reply=True, parse_mode='HTMl')

def editMessage(text: str, message: Message, reply_markup=None):
    try:
        bot.edit_message_text(text=text, message_id=message.message_id,
                              chat_id=message.chat.id,reply_markup=reply_markup,
                              parse_mode='HTMl')
    except Exception as e:
        LOGGER.error(str(e))


def deleteMessage(bot, message: Message):
    try:
        bot.delete_message(chat_id=message.chat.id,
                           message_id=message.message_id)
    except Exception as e:
        LOGGER.error(str(e))


def sendLogFile(bot, update: Update):
    with open('log.txt', 'rb') as f:
        bot.send_document(document=f, filename=f.name,
                          reply_to_message_id=update.message.message_id,
                          chat_id=update.message.chat_id)


def auto_delete_message(bot, cmd_message: Message, bot_message: Message):
    if AUTO_DELETE_MESSAGE_DURATION != -1:
        time.sleep(AUTO_DELETE_MESSAGE_DURATION)
        try:
            # Skip if None is passed meaning we don't want to delete bot xor cmd message
            deleteMessage(bot, cmd_message)
            deleteMessage(bot, bot_message)
        except AttributeError:
            pass


def delete_all_messages():
    with status_reply_dict_lock:
        for message in list(status_reply_dict.values()):
            try:
                deleteMessage(bot, message)
                del status_reply_dict[message.chat.id]
            except Exception as e:
                LOGGER.error(str(e))


def update_all_messages():
    INDEX = 0
        if STATUS_LIMIT is not None:
            dick_no = len(download_dict)
            global pages
            pages = math.ceil(dick_no/STATUS_LIMIT)
            if PAGE_NO > pages and pages != 0:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
        for download in list(download_dict.values()):
            INDEX += 1
            if INDEX > COUNT:
    total, used, free = shutil.disk_usage('.')
    free = get_readable_file_size(free)
    currentTime = get_readable_time(time.time() - botStartTime)
    msg, buttons = get_readable_message()
    if msg is None:
        return
    msg += f"<b>CPU :-</b> {psutil.cpu_percent()}%" \
           f" <b>RAM :-</b> {psutil.virtual_memory().percent}%" \
           f" <b>DISK :-</b> {psutil.disk_usage('/').percent}%"
    with download_dict_lock:
        dlspeed_bytes = 0
        uldl_bytes = 0
        for download in list(download_dict.values()):
            speedy = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in speedy:
                    dlspeed_bytes += float(speedy.split('K')[0]) * 1024
                elif 'M' in speedy:
                    dlspeed_bytes += float(speedy.split('M')[0]) * 1048576 
            if download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in speedy:
                 uldl_bytes += float(speedy.split('K')[0]) * 1024
                elif 'MB/s' in speedy:
                    uldl_bytes += float(speedy.split('M')[0]) * 1048576
        dlspeed = get_readable_file_size(dlspeed_bytes)
        ulspeed = get_readable_file_size(uldl_bytes)
        msg += f"\n<b>FREE :-</b> {free} | <b>UPTIME :-</b> {currentTime}\n<b>DL :-</b> {dlspeed}/s 🔻 | <b>UL :-</b> {ulspeed}/s 🔺\n"
        with status_reply_dict_lock:
        for chat_id in list(status_reply_dict.keys()):
            if status_reply_dict[chat_id] and msg != status_reply_dict[chat_id].text:
                if len(msg) == 0:
                    msg = "Starting DL"
                try:
                    keyboard = [[InlineKeyboardButton("🔃", callback_data=str(ONE)),
                                 InlineKeyboardButton("❌", callback_data=str(TWO)),]]
                    editMessage(msg, status_reply_dict[chat_id], reply_markup=InlineKeyboardMarkup(keyboard))
                except Exception as e:
                    LOGGER.error(str(e))
                status_reply_dict[chat_id].text = msg
                
        if STATUS_LIMIT is not None:
                    if INDEX >= COUNT + STATUS_LIMIT:
                        break
        if STATUS_LIMIT is not None:
            if INDEX > COUNT + STATUS_LIMIT:
                return None, None
            if dick_no > STATUS_LIMIT:
                msg += f"Page: <code>{PAGE_NO}/{pages}</code> | <code>Tasks: {dick_no}</code>\n"
                buttons = button_build.ButtonMaker()
                buttons.sbutton("Previous", "pre")
                buttons.sbutton("Next", "nex")
                button = InlineKeyboardMarkup(buttons.build_menu(2))
                return msg, button
        return msg, ""

def flip(update, context):
    query = update.callback_query
    query.answer()
    global COUNT, PAGE_NO
    if query.data == "nex":
        if PAGE_NO == pages:
            COUNT = 0
            PAGE_NO = 1
        else:
            COUNT += STATUS_LIMIT
            PAGE_NO += 1
    elif query.data == "pre":
        if PAGE_NO == 1:
            COUNT = STATUS_LIMIT * (pages - 1)
            PAGE_NO = pages
        else:
            COUNT -= STATUS_LIMIT
            PAGE_NO -= 1
    message_utils.update_all_messages()
    
                
ONE, TWO = range(2)

def refresh(update, context):
    query = update.callback_query
    query.answer()
    query.edit_message_text(text="Refreshing Status 🥱")
    time.sleep(2)
    update_all_messages()

def close(update, context):
    query = update.callback_query
    query.answer()
    delete_all_messages()                


def sendStatusMessage(msg, bot):
    if len(Interval) == 0:
        Interval.append(setInterval(DOWNLOAD_STATUS_UPDATE_INTERVAL, update_all_messages))
    total, used, free = shutil.disk_usage('.')
    free = get_readable_file_size(free)
    currentTime = get_readable_time(time.time() - botStartTime)
    progress, buttons = get_readable_message()
    if progress is None:
        progress, buttons = get_readable_message()
    progress += f"<b>CPU :-</b> {psutil.cpu_percent()}%" \
           f" <b>RAM :-</b> {psutil.virtual_memory().percent}%" \
           f" <b>DISK :-</b> {psutil.disk_usage('/').percent}%"
    with download_dict_lock:
        dlspeed_bytes = 0
        uldl_bytes = 0
        for download in list(download_dict.values()):
            speedy = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in speedy:
                    dlspeed_bytes += float(speedy.split('K')[0]) * 1024
                elif 'M' in speedy:
                    dlspeed_bytes += float(speedy.split('M')[0]) * 1048576 
            if download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in speedy:
                 uldl_bytes += float(speedy.split('K')[0]) * 1024
                elif 'MB/s' in speedy:
                    uldl_bytes += float(speedy.split('M')[0]) * 1048576
        dlspeed = get_readable_file_size(dlspeed_bytes)
        ulspeed = get_readable_file_size(uldl_bytes)
        progress += f"\n<b>FREE :-</b> {free} | <b>UPTIME :-</b> {currentTime}\n<b>DL :-</b> {dlspeed}/s 🔻 | <b>UL :-</b> {ulspeed}/s 🔺\n"
    with status_reply_dict_lock:
        if msg.message.chat.id in list(status_reply_dict.keys()):
            try:
                message = status_reply_dict[msg.message.chat.id]
                deleteMessage(bot, message)
                del status_reply_dict[msg.message.chat.id]
            except Exception as e:
                LOGGER.error(str(e))
                del status_reply_dict[msg.message.chat.id]
                pass
        if buttons == "":
            message = sendMessage(progress, bot, msg)
        else:
            message = sendMarkup(progress, bot, msg, buttons)
        status_reply_dict[msg.message.chat.id] = message
       
dispatcher.add_handler(CallbackQueryHandler(refresh, pattern='^' + str(ONE) + '$'))
dispatcher.add_handler(CallbackQueryHandler(close, pattern='^' + str(TWO) + '$'))    
next_handler = CallbackQueryHandler(flip, pattern="nex", run_async=True)
previous_handler = CallbackQueryHandler(flip, pattern="pre", run_async=True)
dispatcher.add_handler(next_handler)
dispatcher.add_handler(previous_handler)

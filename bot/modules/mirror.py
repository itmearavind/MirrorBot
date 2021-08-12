import requests
from telegram.ext import commandhandler
from telegram import inlinekeyboardmarkup

from bot import interval, index_url, button_four_name, button_four_url, button_five_name, button_five_url, button_six_name, button_six_url, block_mega_folder, block_mega_links, view_link, aria2, get_client
from bot import dispatcher, download_dir, download_dict, download_dict_lock, shortener, shortener_api, tar_unzip_limit
from bot.helper.ext_utils import fs_utils, bot_utils
from bot.helper.ext_utils.bot_utils import get_mega_link_type
from bot.helper.ext_utils.exceptions import directdownloadlinkexception, notsupportedextractionarchive
from bot.helper.mirror_utils.download_utils.aria2_download import ariadownloadhelper
from bot.helper.mirror_utils.download_utils.mega_downloader import megadownloadhelper
from bot.helper.mirror_utils.download_utils.qbit_downloader import qbittorrent
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_downloader import telegramdownloadhelper
from bot.helper.mirror_utils.status_utils import listeners
from bot.helper.mirror_utils.status_utils.extract_status import extractstatus
from bot.helper.mirror_utils.status_utils.tar_status import tarstatus
from bot.helper.mirror_utils.status_utils.upload_status import uploadstatus
from bot.helper.mirror_utils.status_utils.gdownload_status import downloadstatus
from bot.helper.mirror_utils.upload_utils import gdrivetools
from bot.helper.telegram_helper.bot_commands import botcommands
from bot.helper.telegram_helper.filters import customfilters
from bot.helper.telegram_helper.message_utils import *
from bot.helper.telegram_helper import button_build
import urllib
import pathlib
import os
import subprocess
import threading
import re
import random
import string

ariadlmanager = ariadownloadhelper()
ariadlmanager.start_listener()

class mirrorlistener(listeners.mirrorlisteners):
    def __init__(self, bot, update, pswd, istar=false, extract=false, qbit=false):
        super().__init__(bot, update)
        self.istar = istar
        self.extract = extract
        self.qbit = qbit
        self.pswd = pswd

    def ondownloadstarted(self):
        pass

    def ondownloadprogress(self):
        # we are handling this on our own!
        pass

    def clean(self):
        try:
            aria2.purge()
            get_client().torrents_delete(torrent_hashes="all", delete_files=true)
            interval[0].cancel()
            del interval[0]
            delete_all_messages()
        except indexerror:
            pass

    def ondownloadcomplete(self):
        with download_dict_lock:
            logger.info(f"download completed: {download_dict[self.uid].name()}")
            download = download_dict[self.uid]
            name = download.name()
            gid = download.gid()
            size = download.size_raw()
            if name is none or self.qbit: # when pyrogram's media.file_name is of nonetype
                name = os.listdir(f'{download_dir}{self.uid}')[0]
            m_path = f'{download_dir}{self.uid}/{name}'
        if self.istar:
            try:
                with download_dict_lock:
                    download_dict[self.uid] = tarstatus(name, m_path, size)
                path = fs_utils.tar(m_path)
            except filenotfounderror:
                logger.info('file to archive not found!')
                self.onuploaderror('internal error occurred!!')
                return
        elif self.extract:
            try:
                path = fs_utils.get_base_name(m_path)
                logger.info(f"extracting: {name}")
                with download_dict_lock:
                    download_dict[self.uid] = extractstatus(name, m_path, size)
                pswd = self.pswd
                if pswd is not none:
                    archive_result = subprocess.run(["pextract", m_path, pswd])
                else:
                    archive_result = subprocess.run(["extract", m_path])
                if archive_result.returncode == 0:
                    threading.thread(target=os.remove, args=(m_path,)).start()
                    logger.info(f"deleting archive: {m_path}")
                else:
                    logger.warning('unable to extract archive! uploading anyway')
                    path = f'{download_dir}{self.uid}/{name}'
                logger.info(f'got path: {path}')

            except notsupportedextractionarchive:
                logger.info("not any valid archive, uploading file as it is.")
                path = f'{download_dir}{self.uid}/{name}'
        else:
            path = f'{download_dir}{self.uid}/{name}'
        up_name = pathlib.purepath(path).name
        up_path = f'{download_dir}{self.uid}/{up_name}'
        logger.info(f"upload name: {up_name}")
        drive = gdrivetools.googledrivehelper(up_name, self)
        size = fs_utils.get_path_size(up_path)
        upload_status = uploadstatus(drive, size, gid, self)
        with download_dict_lock:
            download_dict[self.uid] = upload_status
        update_all_messages()
        drive.upload(up_name)

    def ondownloaderror(self, error):
        error = error.replace('<', ' ')
        error = error.replace('>', ' ')
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                fs_utils.clean_download(download.path())
            except exception as e:
                logger.error(str(e))
                pass
            count = len(download_dict)
        if self.message.from_user.username:
            uname = f"@{self.message.from_user.username}"
        else:
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} your download has been stopped due to: {error}"
        sendmessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onuploadstarted(self):
        pass

    def onuploadprogress(self):
        pass

    def onuploadcomplete(self, link: str, size, files, folders, typ):
        with download_dict_lock:
            msg = f'<b>filename: </b><code>{download_dict[self.uid].name()}</code>\n<b>size: </b><code>{size}</code>'
            if os.path.isdir(f'{download_dir}/{self.uid}/{download_dict[self.uid].name()}'):
                msg += '\n<b>type: </b><code>folder</code>'
                msg += f'\n<b>subfolders: </b><code>{folders}</code>'
                msg += f'\n<b>files: </b><code>{files}</code>'
            else:
                msg += f'\n<b>type: </b><code>{typ}</code>'
            buttons = button_build.buttonmaker()
            if shortener is not none and shortener_api is not none:
                surl = requests.get(f'https://{shortener}/api?api={shortener_api}&url={link}&format=text').text
                buttons.buildbutton("☁️ drive link", surl)
            else:
                buttons.buildbutton("☁️ drive link", link)
            logger.info(f'done uploading {download_dict[self.uid].name()}')
            if index_url is not none:
                url_path = requests.utils.quote(f'{download_dict[self.uid].name()}')
                share_url = f'{index_url}/{url_path}'
                if os.path.isdir(f'{download_dir}/{self.uid}/{download_dict[self.uid].name()}'):
                    share_url += '/'
                    if shortener is not none and shortener_api is not none:
                        siurl = requests.get(f'https://{shortener}/api?api={shortener_api}&url={share_url}&format=text').text
                        buttons.buildbutton("⚡ index link", siurl)
                    else:
                        buttons.buildbutton("⚡ index link", share_url)
                else:
                    share_urls = f'{index_url}/{url_path}?a=view'
                    if shortener is not none and shortener_api is not none:
                        siurl = requests.get(f'https://{shortener}/api?api={shortener_api}&url={share_url}&format=text').text
                        siurls = requests.get(f'https://{shortener}/api?api={shortener_api}&url={share_urls}&format=text').text
                        buttons.buildbutton("⚡ index link", siurl)
                        if view_link:
                            buttons.buildbutton("🌐 view link", siurls)
                    else:
                        buttons.buildbutton("⚡ index link", share_url)
                        if view_link:
                            buttons.buildbutton("🌐 view link", share_urls)
            if button_four_name is not none and button_four_url is not none:
                buttons.buildbutton(f"{button_four_name}", f"{button_four_url}")
            if button_five_name is not none and button_five_url is not none:
                buttons.buildbutton(f"{button_five_name}", f"{button_five_url}")
            if button_six_name is not none and button_six_url is not none:
                buttons.buildbutton(f"{button_six_name}", f"{button_six_url}")
            if self.message.from_user.username:
                uname = f"@{self.message.from_user.username}"
            else:
                uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
            if uname is not none:
                msg += f'\n\ncc: {uname}'
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except filenotfounderror:
                pass
            del download_dict[self.uid]
            count = len(download_dict)
        sendmarkup(msg, self.bot, self.update, inlinekeyboardmarkup(buttons.build_menu(2)))
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onuploaderror(self, error):
        e_str = error.replace('<', '').replace('>', '')
        with download_dict_lock:
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except filenotfounderror:
                pass
            del download_dict[self.message.message_id]
            count = len(download_dict)
        if self.message.from_user.username:
            uname = f"@{self.message.from_user.username}"
        else:
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        if uname is not none:
            men = f'{uname} '
        sendmessage(men + e_str, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

def _mirror(bot, update, istar=false, extract=false):
    mesg = update.message.text.split('\n')
    message_args = mesg[0].split(' ')
    name_args = mesg[0].split('|')
    qbit = false
    qbitsel = false
    try:
        link = message_args[1]
        if link == "qb" or link == "qbs":
            qbit = true
            if link == "qbs":
                qbitsel = true
            link = message_args[2]
        print(link)
        if link.startswith("|") or link.startswith("pswd: "):
            link = ''
    except indexerror:
        link = ''
    try:
        name = name_args[1]
        name = name.strip()
        if name.startswith("pswd: "):
            name = ''
    except indexerror:
        name = ''
    try:
        ussr = urllib.parse.quote(mesg[1], safe='')
        pssw = urllib.parse.quote(mesg[2], safe='')
    except:
        ussr = ''
        pssw = ''
    if ussr != '' and pssw != '':
        link = link.split("://", maxsplit=1)
        link = f'{link[0]}://{ussr}:{pssw}@{link[1]}'
    pswd = re.search('(?<=pswd: )(.*)', update.message.text)
    if pswd is not none:
      pswd = pswd.groups()
      pswd = " ".join(pswd)
    logger.info(link)
    link = link.strip()
    reply_to = update.message.reply_to_message
    if reply_to is not none:
        file = none
        media_array = [reply_to.document, reply_to.video, reply_to.audio]
        for i in media_array:
            if i is not none:
                file = i
                break

        if not bot_utils.is_url(link) and not bot_utils.is_magnet(link) or len(link) == 0:
            if file is not none:
                if file.mime_type != "application/x-bittorrent":
                    listener = mirrorlistener(bot, update, pswd, istar, extract)
                    tg_downloader = telegramdownloadhelper(listener)
                    ms = update.message
                    tg_downloader.add_download(ms, f'{download_dir}{listener.uid}/', name)
                    return
                else:
                    if qbit:
                        file.get_file().download(custom_path=f"/usr/src/app/{file.file_name}")
                        link = f"/usr/src/app/{file.file_name}"
                    else:
                        link = file.get_file().file_path

    if not bot_utils.is_url(link) and not bot_utils.is_magnet(link):
        sendmessage('no download source provided', bot, update)
        return

    try:
        link = direct_link_generator(link)
    except directdownloadlinkexception as e:
        logger.info(e)
        if "error:" in str(e):
            sendmessage(f"{e}", bot, update)
            return
        if "youtube" in str(e):
            sendmessage(f"{e}", bot, update)
            return

    listener = mirrorlistener(bot, update, pswd, istar, extract, qbit)

    if bot_utils.is_gdrive_link(link):
        if not istar and not extract:
            sendmessage(f"use /{botcommands.clonecommand} to clone google drive file/folder\nuse /{botcommands.tarmirrorcommand} to make tar of google drive folder\nuse /{botcommands.unzipmirrorcommand} to extracts archive google drive file", bot, update)
            return
        res, size, name, files = gdrivetools.googledrivehelper().clonehelper(link)
        if res != "":
            sendmessage(res, bot, update)
            return
        if tar_unzip_limit is not none:
            logger.info(f'checking file/folder size')
            limit = tar_unzip_limit
            limit = limit.split(' ', maxsplit=1)
            limitint = int(limit[0])
            msg = f'failed, tar/unzip limit is {tar_unzip_limit}.\nyour file/folder size is {get_readable_file_size(size)}.'
            if 'g' in limit[1] or 'g' in limit[1]:
                if size > limitint * 1024**3:
                    sendmessage(msg, listener.bot, listener.update)
                    return
            elif 't' in limit[1] or 't' in limit[1]:
                if size > limitint * 1024**4:
                    sendmessage(msg, listener.bot, listener.update)
                    return
        logger.info(f"download name : {name}")
        drive = gdrivetools.googledrivehelper(name, listener)
        gid = ''.join(random.systemrandom().choices(string.ascii_letters + string.digits, k=12))
        download_status = downloadstatus(drive, size, listener, gid)
        with download_dict_lock:
            download_dict[listener.uid] = download_status
        sendstatusmessage(update, bot)
        drive.download(link)

    elif bot_utils.is_mega_link(link):
        link_type = get_mega_link_type(link)
        if link_type == "folder" and block_mega_folder:
            sendmessage("mega folder are blocked!", bot, update)
        elif block_mega_links:
            sendmessage("mega links are blocked!", bot, update)
        else:
            mega_dl = megadownloadhelper()
            mega_dl.add_download(link, f'{download_dir}/{listener.uid}/', listener)

    elif qbit and (bot_utils.is_magnet(link) or os.path.exists(link)):
        qbit = qbittorrent()
        qbit.add_torrent(link, f'{download_dir}{listener.uid}/', listener, qbitsel)

    else:
        ariadlmanager.add_download(link, f'{download_dir}/{listener.uid}/', listener, name)
        sendstatusmessage(update, bot)


def mirror(update, context):
    _mirror(context.bot, update)


def tar_mirror(update, context):
    _mirror(context.bot, update, true)


def unzip_mirror(update, context):
    _mirror(context.bot, update, extract=true)


mirror_handler = commandhandler(botcommands.mirrorcommand, mirror,
                                filters=customfilters.authorized_chat | customfilters.authorized_user, run_async=true)
tar_mirror_handler = commandhandler(botcommands.tarmirrorcommand, tar_mirror,
                                    filters=customfilters.authorized_chat | customfilters.authorized_user, run_async=true)
unzip_mirror_handler = commandhandler(botcommands.unzipmirrorcommand, unzip_mirror,
                                      filters=customfilters.authorized_chat | customfilters.authorized_user, run_async=true)
dispatcher.add_handler(mirror_handler)
dispatcher.add_handler(tar_mirror_handler)
dispatcher.add_handler(unzip_mirror_handler)
import requests
from telegram.ext import CommandHandler
from telegram import InlineKeyboardMarkup

from bot import Interval, INDEX_URL, BUTTON_FOUR_NAME, BUTTON_FOUR_URL, BUTTON_FIVE_NAME, BUTTON_FIVE_URL, BUTTON_SIX_NAME, BUTTON_SIX_URL, BLOCK_MEGA_FOLDER, BLOCK_MEGA_LINKS, VIEW_LINK, aria2, get_client
from bot import dispatcher, DOWNLOAD_DIR, download_dict, download_dict_lock, SHORTENER, SHORTENER_API, TAR_UNZIP_LIMIT
from bot.helper.ext_utils import fs_utils, bot_utils
from bot.helper.ext_utils.bot_utils import get_mega_link_type
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException, NotSupportedExtractionArchive
from bot.helper.mirror_utils.download_utils.aria2_download import AriaDownloadHelper
from bot.helper.mirror_utils.download_utils.mega_downloader import MegaDownloadHelper
from bot.helper.mirror_utils.download_utils.qbit_downloader import qbittorrent
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_downloader import TelegramDownloadHelper
from bot.helper.mirror_utils.status_utils import listeners
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.tar_status import TarStatus
from bot.helper.mirror_utils.status_utils.upload_status import UploadStatus
from bot.helper.mirror_utils.status_utils.gdownload_status import DownloadStatus
from bot.helper.mirror_utils.upload_utils import gdriveTools
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import *
from bot.helper.telegram_helper import button_build
import urllib
import pathlib
import os
import subprocess
import threading
import re
import random
import string

ariaDlManager = AriaDownloadHelper()
ariaDlManager.start_listener()

class MirrorListener(listeners.MirrorListeners):
    def __init__(self, bot, update, pswd, isTar=False, extract=False, qbit=False):
        super().__init__(bot, update)
        self.isTar = isTar
        self.extract = extract
        self.qbit = qbit
        self.pswd = pswd

    def onDownloadStarted(self):
        pass

    def onDownloadProgress(self):
        # We are handling this on our own!
        pass

    def clean(self):
        try:
            aria2.purge()
            get_client().torrents_delete(torrent_hashes="all", delete_files=True)
            Interval[0].cancel()
            del Interval[0]
            delete_all_messages()
        except IndexError:
            pass

    def onDownloadComplete(self):
        with download_dict_lock:
            LOGGER.info(f"Download completed: {download_dict[self.uid].name()}")
            download = download_dict[self.uid]
            name = download.name()
            gid = download.gid()
            size = download.size_raw()
            if name is None or self.qbit: # when pyrogram's media.file_name is of NoneType
                name = os.listdir(f'{DOWNLOAD_DIR}{self.uid}')[0]
            m_path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        if self.isTar:
            try:
                with download_dict_lock:
                    download_dict[self.uid] = TarStatus(name, m_path, size)
                path = fs_utils.tar(m_path)
            except FileNotFoundError:
                LOGGER.info('File to archive not found!')
                self.onUploadError('Internal error occurred!!')
                return
        elif self.extract:
            try:
                path = fs_utils.get_base_name(m_path)
                LOGGER.info(f"Extracting: {name}")
                with download_dict_lock:
                    download_dict[self.uid] = ExtractStatus(name, m_path, size)
                pswd = self.pswd
                if pswd is not None:
                    archive_result = subprocess.run(["pextract", m_path, pswd])
                else:
                    archive_result = subprocess.run(["extract", m_path])
                if archive_result.returncode == 0:
                    threading.Thread(target=os.remove, args=(m_path,)).start()
                    LOGGER.info(f"Deleting archive: {m_path}")
                else:
                    LOGGER.warning('Unable to extract archive! Uploading anyway')
                    path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
                LOGGER.info(f'got path: {path}')

            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        else:
            path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        up_name = pathlib.PurePath(path).name
        up_path = f'{DOWNLOAD_DIR}{self.uid}/{up_name}'
        LOGGER.info(f"Upload Name: {up_name}")
        drive = gdriveTools.GoogleDriveHelper(up_name, self)
        size = fs_utils.get_path_size(up_path)
        upload_status = UploadStatus(drive, size, gid, self)
        with download_dict_lock:
            download_dict[self.uid] = upload_status
        update_all_messages()
        drive.upload(up_name)

    def onDownloadError(self, error):
        error = error.replace('<', ' ')
        error = error.replace('>', ' ')
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                fs_utils.clean_download(download.path())
            except Exception as e:
                LOGGER.error(str(e))
                pass
            count = len(download_dict)
        if self.message.from_user.username:
            uname = f"@{self.message.from_user.username}"
        else:
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} your download has been stopped due to: {error}"
        sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onUploadStarted(self):
        pass

    def onUploadProgress(self):
        pass

    def onUploadComplete(self, link: str, size, files, folders, typ):
        with download_dict_lock:
            msg = f'<b>Filename: </b><code>{download_dict[self.uid].name()}</code>\n<b>Size: </b><code>{size}</code>'
            if os.path.isdir(f'{DOWNLOAD_DIR}/{self.uid}/{download_dict[self.uid].name()}'):
                msg += '\n<b>Type: </b><code>Folder</code>'
                msg += f'\n<b>SubFolders: </b><code>{folders}</code>'
                msg += f'\n<b>Files: </b><code>{files}</code>'
            else:
                msg += f'\n<b>Type: </b><code>{typ}</code>'
            buttons = button_build.ButtonMaker()
            if SHORTENER is not None and SHORTENER_API is not None:
                surl = requests.get(f'https://{SHORTENER}/api?api={SHORTENER_API}&url={link}&format=text').text
                buttons.buildbutton("☁️ Drive Link", surl)
            else:
                buttons.buildbutton("☁️ Drive Link", link)
            LOGGER.info(f'Done Uploading {download_dict[self.uid].name()}')
            if INDEX_URL is not None:
                url_path = requests.utils.quote(f'{download_dict[self.uid].name()}')
                share_url = f'{INDEX_URL}/{url_path}'
                if os.path.isdir(f'{DOWNLOAD_DIR}/{self.uid}/{download_dict[self.uid].name()}'):
                    share_url += '/'
                    if SHORTENER is not None and SHORTENER_API is not None:
                        siurl = requests.get(f'https://{SHORTENER}/api?api={SHORTENER_API}&url={share_url}&format=text').text
                        buttons.buildbutton("⚡ Index Link", siurl)
                    else:
                        buttons.buildbutton("⚡ Index Link", share_url)
                else:
                    share_urls = f'{INDEX_URL}/{url_path}?a=view'
                    if SHORTENER is not None and SHORTENER_API is not None:
                        siurl = requests.get(f'https://{SHORTENER}/api?api={SHORTENER_API}&url={share_url}&format=text').text
                        siurls = requests.get(f'https://{SHORTENER}/api?api={SHORTENER_API}&url={share_urls}&format=text').text
                        buttons.buildbutton("⚡ Index Link", siurl)
                        if VIEW_LINK:
                            buttons.buildbutton("🌐 View Link", siurls)
                    else:
                        buttons.buildbutton("⚡ Index Link", share_url)
                        if VIEW_LINK:
                            buttons.buildbutton("🌐 View Link", share_urls)
            if BUTTON_FOUR_NAME is not None and BUTTON_FOUR_URL is not None:
                buttons.buildbutton(f"{BUTTON_FOUR_NAME}", f"{BUTTON_FOUR_URL}")
            if BUTTON_FIVE_NAME is not None and BUTTON_FIVE_URL is not None:
                buttons.buildbutton(f"{BUTTON_FIVE_NAME}", f"{BUTTON_FIVE_URL}")
            if BUTTON_SIX_NAME is not None and BUTTON_SIX_URL is not None:
                buttons.buildbutton(f"{BUTTON_SIX_NAME}", f"{BUTTON_SIX_URL}")
            if self.message.from_user.username:
                uname = f"@{self.message.from_user.username}"
            else:
                uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
            if uname is not None:
                msg += f'\n\ncc: {uname}'
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.uid]
            count = len(download_dict)
        sendMarkup(msg, self.bot, self.update, InlineKeyboardMarkup(buttons.build_menu(2)))
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onUploadError(self, error):
        e_str = error.replace('<', '').replace('>', '')
        with download_dict_lock:
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.message.message_id]
            count = len(download_dict)
        if self.message.from_user.username:
            uname = f"@{self.message.from_user.username}"
        else:
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        if uname is not None:
            men = f'{uname} '
        sendMessage(men + e_str, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

def _mirror(bot, update, isTar=False, extract=False):
    mesg = update.message.text.split('\n')
    message_args = mesg[0].split(' ')
    name_args = mesg[0].split('|')
    qbit = False
    qbitsel = False
    try:
        link = message_args[1]
        if link == "qb" or link == "qbs":
            qbit = True
            if link == "qbs":
                qbitsel = True
            link = message_args[2]
        print(link)
        if link.startswith("|") or link.startswith("pswd: "):
            link = ''
    except IndexError:
        link = ''
    try:
        name = name_args[1]
        name = name.strip()
        if name.startswith("pswd: "):
            name = ''
    except IndexError:
        name = ''
    try:
        ussr = urllib.parse.quote(mesg[1], safe='')
        pssw = urllib.parse.quote(mesg[2], safe='')
    except:
        ussr = ''
        pssw = ''
    if ussr != '' and pssw != '':
        link = link.split("://", maxsplit=1)
        link = f'{link[0]}://{ussr}:{pssw}@{link[1]}'
    pswd = re.search('(?<=pswd: )(.*)', update.message.text)
    if pswd is not None:
      pswd = pswd.groups()
      pswd = " ".join(pswd)
    LOGGER.info(link)
    link = link.strip()
    reply_to = update.message.reply_to_message
    if reply_to is not None:
        file = None
        media_array = [reply_to.document, reply_to.video, reply_to.audio]
        for i in media_array:
            if i is not None:
                file = i
                break

        if not bot_utils.is_url(link) and not bot_utils.is_magnet(link) or len(link) == 0:
            if file is not None:
                if file.mime_type != "application/x-bittorrent":
                    listener = MirrorListener(bot, update, pswd, isTar, extract)
                    tg_downloader = TelegramDownloadHelper(listener)
                    ms = update.message
                    tg_downloader.add_download(ms, f'{DOWNLOAD_DIR}{listener.uid}/', name)
                    return
                else:
                    if qbit:
                        file.get_file().download(custom_path=f"/usr/src/app/{file.file_name}")
                        link = f"/usr/src/app/{file.file_name}"
                    else:
                        link = file.get_file().file_path

    if not bot_utils.is_url(link) and not bot_utils.is_magnet(link):
        sendMessage('No download source provided', bot, update)
        return

    try:
        link = direct_link_generator(link)
    except DirectDownloadLinkException as e:
        LOGGER.info(e)
        if "ERROR:" in str(e):
            sendMessage(f"{e}", bot, update)
            return
        if "Youtube" in str(e):
            sendMessage(f"{e}", bot, update)
            return

    listener = MirrorListener(bot, update, pswd, isTar, extract, qbit)

    if bot_utils.is_gdrive_link(link):
        if not isTar and not extract:
            sendMessage(f"Use /{BotCommands.CloneCommand} to clone Google Drive file/folder\nUse /{BotCommands.TarMirrorCommand} to make tar of Google Drive folder\nUse /{BotCommands.UnzipMirrorCommand} to extracts archive Google Drive file", bot, update)
            return
        res, size, name, files = gdriveTools.GoogleDriveHelper().clonehelper(link)
        if res != "":
            sendMessage(res, bot, update)
            return
        if TAR_UNZIP_LIMIT is not None:
            LOGGER.info(f'Checking File/Folder Size')
            limit = TAR_UNZIP_LIMIT
            limit = limit.split(' ', maxsplit=1)
            limitint = int(limit[0])
            msg = f'Failed, Tar/Unzip limit is {TAR_UNZIP_LIMIT}.\nYour File/Folder size is {get_readable_file_size(size)}.'
            if 'G' in limit[1] or 'g' in limit[1]:
                if size > limitint * 1024**3:
                    sendMessage(msg, listener.bot, listener.update)
                    return
            elif 'T' in limit[1] or 't' in limit[1]:
                if size > limitint * 1024**4:
                    sendMessage(msg, listener.bot, listener.update)
                    return
        LOGGER.info(f"Download Name : {name}")
        drive = gdriveTools.GoogleDriveHelper(name, listener)
        gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=12))
        download_status = DownloadStatus(drive, size, listener, gid)
        with download_dict_lock:
            download_dict[listener.uid] = download_status
        sendStatusMessage(update, bot)
        drive.download(link)

    elif bot_utils.is_mega_link(link):
        link_type = get_mega_link_type(link)
        if link_type == "folder" and BLOCK_MEGA_FOLDER:
            sendMessage("Mega folder are blocked!", bot, update)
        elif BLOCK_MEGA_LINKS:
            sendMessage("Mega links are blocked!", bot, update)
        else:
            mega_dl = MegaDownloadHelper()
            mega_dl.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/', listener)

    elif qbit and (bot_utils.is_magnet(link) or os.path.exists(link)):
        qbit = qbittorrent()
        qbit.add_torrent(link, f'{DOWNLOAD_DIR}{listener.uid}/', listener, qbitsel)

    else:
        ariaDlManager.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/', listener, name)
        sendStatusMessage(update, bot)


def mirror(update, context):
    _mirror(context.bot, update)


def tar_mirror(update, context):
    _mirror(context.bot, update, True)


def unzip_mirror(update, context):
    _mirror(context.bot, update, extract=True)


mirror_handler = CommandHandler(BotCommands.MirrorCommand, mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
tar_mirror_handler = CommandHandler(BotCommands.TarMirrorCommand, tar_mirror,
                                    filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
unzip_mirror_handler = CommandHandler(BotCommands.UnzipMirrorCommand, unzip_mirror,
                                      filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
dispatcher.add_handler(mirror_handler)
dispatcher.add_handler(tar_mirror_handler)
dispatcher.add_handler(unzip_mirror_handler)

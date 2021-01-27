from telegram.ext import CommandHandler, run_async
from bot.gDrive import GoogleDriveHelper
from bot.fs_utils import get_readable_file_size
from bot import LOGGER, dispatcher, updater, bot
from bot.config import BOT_TOKEN, OWNER_ID, GDRIVE_FOLDER_ID
from bot.decorators import is_authorised, is_owner
from telegram.error import TimedOut, BadRequest
from bot.clone_status import CloneStatus
from bot.msg_utils import deleteMessage, sendMessage
import time

REPO_LINK = "https://Telegram.me/DKzippO"
# Soon to be used for direct updates from within the bot.

@run_async
def start(update, context):
    sendMessage("¡Hola! Envíeme un enlace para compartir de Google Drive para clonar en su unidad." \
        "\nEnvía /help para comprobar todos los comandos disponibles." \
                "\nSi quieres conocer los canales del creador del bot revisa @CanalesFamosos 😏❤️",
    context.bot, update, 'Markdown')
    # ;-;

@run_async
def helper(update, context):
    sendMessage("Aquí están los comandos disponibles del bot\n\n" \
        "*Usa:* `/clone <link> [DESTINATION_ID]`\n*Ejemplo:* \n1. `/clone https://drive.google.com/drive/u/1/folders/0AO-ISIXXXXXXXXXXXX`\n2. `/clone 0AO-ISIXXXXXXXXXXXX`" \
            "\n*El ID de destino* es opcional. Puede ser un enlace o un ID al lugar donde desea almacenar un clon en particular." \
            "\n\nTambién puede *ignorar carpetas* del proceso de clonación haciendo lo siguiente:\n" \
                "`/clone <FOLDER_ID> [DESTINATION] [id1,id2,id3]`\n En este ejemplo: id1, id2 and id3 sería ignorado por la clonación\nNo utilice <> o [] en el mensaje actual." \
                    "*Asegúrate de no poner ningún espacio entre comas. (,)*\n" \
                        f"*Creador del bot:* [Skueletor]({REPO_LINK})", context.bot, update, 'Markdown')

# TODO Cancel Clones with /cancel command.
@run_async
@is_authorised
def cloneNode(update, context):
    args = update.message.text.split(" ")
    if len(args) > 1:
        link = args[1]
        try:
            ignoreList = args[-1].split(',')
        except IndexError:
            ignoreList = []

        DESTINATION_ID = GDRIVE_FOLDER_ID
        try:
            DESTINATION_ID = args[2]
            print(DESTINATION_ID)
        except IndexError:
            pass
            # Usage: /clone <FolderToClone> <Destination> <IDtoIgnoreFromClone>,<IDtoIgnoreFromClone>

        msg = sendMessage(f"<b>Clonando:</b> <code>{link}</code>", context.bot, update)
        status_class = CloneStatus()
        gd = GoogleDriveHelper(GFolder_ID=DESTINATION_ID)
        sendCloneStatus(update, context, status_class, msg, link)
        result = gd.clone(link, status_class, ignoreList=ignoreList)
        deleteMessage(context.bot, msg)
        status_class.set_status(True)
        sendMessage(result, context.bot, update)
    else:
        sendMessage("Proporcione un enlace compartido de Google Drive para clonar.", bot, update)


@run_async
def sendCloneStatus(update, context, status, msg, link):
    old_text = ''
    while not status.done():
        sleeper(3)
        try:
            text=f'🔗 *Clonando:* [{status.MainFolderName}]({status.MainFolderLink})\n━━━━━━━━━━━━━━\n🗃️ *Archivo actual:* `{status.get_name()}`\n⬆️ *Transferido*: `{status.get_size()}`\n📁 *Destino:* [{status.DestinationFolderName}]({status.DestinationFolderLink})'
            if status.checkFileStatus():
                text += f"\n🕒 *Comprobación de archivos existentes:* `{str(status.checkFileStatus())}`"
            if not text == old_text:
                msg.edit_text(text=text, parse_mode="Markdown", timeout=200)
                old_text = text
        except Exception as e:
            LOGGER.error(e)
            if str(e) == "Mensaje para editar no encontrado":
                break
            sleeper(2)
            continue
    return

def sleeper(value, enabled=True):
    time.sleep(int(value))
    return

@run_async
@is_owner
def sendLogs(update, context):
    with open('log.txt', 'rb') as f:
        bot.send_document(document=f, filename=f.name,
                        reply_to_message_id=update.message.message_id,
                        chat_id=update.message.chat_id)

def main():
    LOGGER.info("Bot iniciado!")
    clone_handler = CommandHandler('clone', cloneNode)
    start_handler = CommandHandler('start', start)
    help_handler = CommandHandler('help', helper)
    log_handler = CommandHandler('logs', sendLogs)
    dispatcher.add_handler(log_handler)
    dispatcher.add_handler(start_handler)
    dispatcher.add_handler(clone_handler)
    dispatcher.add_handler(help_handler)
    updater.start_polling()

main()

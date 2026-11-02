import asyncio
import re
import logging

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import BOT_TOKEN, OWNER_ID
from database import (
    get_wallet,
    add_wallet,
    remove_wallet,
)

from monitor import monitor_loop

logger = logging.getLogger(__name__)

MENU = [
    ["➕ Add Wallet", "👛 My Wallet"],
    ["🗑 Remove Wallet", "📊 Status"],
    ["❓ Help"],
]

KEYBOARD = ReplyKeyboardMarkup(
    MENU,
    resize_keyboard=True,
    is_persistent=True,
)


def is_owner(user):
    return user is not None and user.id == OWNER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user):
        return

    context.user_data.pop("awaiting_wallet", None)

    await update.message.reply_text(
        "👋 <b>Welcome to BlockWatcher!</b>\n\n"
        "Your private Ethereum wallet monitor is ready.\n"
        "Choose an option below.",
        parse_mode="HTML",
        reply_markup=KEYBOARD,
    )


async def add_wallet_start(update, context):
    if not is_owner(update.effective_user):
        return

    if get_wallet():
        await update.message.reply_text(
            "⚠️ You already have a wallet registered.\n"
            "Remove the current wallet before adding another.",
            reply_markup=KEYBOARD,
        )
        return

    context.user_data["awaiting_wallet"] = True

    await update.message.reply_text(
        "➕ <b>Add Ethereum Wallet</b>\n\n"
        "Send the wallet address you want to monitor.\n\n"
        "Send /cancel to cancel.",
        parse_mode="HTML",
        reply_markup=KEYBOARD,
    )


async def process_wallet(update, context):
    if not is_owner(update.effective_user):
        return

    address = update.message.text.strip()

    if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
        await update.message.reply_text(
            "❌ Invalid Ethereum address.\n"
            "Please send a valid address containing 42 characters.",
            reply_markup=KEYBOARD,
        )
        return

    if not add_wallet(address):
        context.user_data.pop("awaiting_wallet", None)

        await update.message.reply_text(
            "⚠️ A wallet is already registered.",
            reply_markup=KEYBOARD,
        )
        return

    context.user_data.pop("awaiting_wallet", None)

    await update.message.reply_text(
        "✅ <b>Wallet added successfully!</b>\n\n"
        f"<code>{address.lower()}</code>\n\n"
        "BlockWatcher will establish its monitoring baseline shortly.",
        parse_mode="HTML",
        reply_markup=KEYBOARD,
    )


async def cancel(update, context):
    if not is_owner(update.effective_user):
        return

    context.user_data.pop("awaiting_wallet", None)

    await update.message.reply_text(
        "❌ Operation cancelled.",
        reply_markup=KEYBOARD,
    )


async def remove_wallet_start(update, context):
    if not is_owner(update.effective_user):
        return

    wallet = get_wallet()

    if not wallet:
        await update.message.reply_text(
            "You don't have a registered wallet.",
            reply_markup=KEYBOARD,
        )
        return

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Yes, remove",
                callback_data="remove_confirm",
            ),
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="remove_cancel",
            ),
        ]
    ])

    await update.message.reply_text(
        "⚠️ <b>Remove registered wallet?</b>\n\n"
        f"<code>{wallet}</code>\n\n"
        "Are you sure?",
        parse_mode="HTML",
        reply_markup=buttons,
    )


async def remove_callback(update, context):
    query = update.callback_query

    if not is_owner(update.effective_user):
        await query.answer("Unauthorized.", show_alert=True)
        return

    await query.answer()

    if query.data == "remove_confirm":
        remove_wallet()
        await query.edit_message_text(
            "✅ Wallet removed successfully."
        )

    elif query.data == "remove_cancel":
        await query.edit_message_text(
            "❌ Removal cancelled."
        )


async def my_wallet(update, context):
    if not is_owner(update.effective_user):
        return

    wallet = get_wallet()

    if not wallet:
        await update.message.reply_text(
            "👛 No wallet registered yet.",
            reply_markup=KEYBOARD,
        )
        return

    await update.message.reply_text(
        "👛 <b>Your Registered Wallet</b>\n\n"
        f"<code>{wallet}</code>",
        parse_mode="HTML",
        reply_markup=KEYBOARD,
    )


async def status(update, context):
    if not is_owner(update.effective_user):
        return

    wallet = get_wallet()
    task = context.application.bot_data.get("monitor_task")

    monitor_online = task is not None and not task.done()

    await update.message.reply_text(
        "📊 <b>BlockWatcher Status</b>\n\n"
        f"👛 Wallet: <b>{'Registered' if wallet else 'Not registered'}</b>\n"
        f"⚙️ Monitor: <b>{'Running' if monitor_online else 'Stopped'}</b>"
        + (f"\n\n<code>{wallet}</code>" if wallet else ""),
        parse_mode="HTML",
        reply_markup=KEYBOARD,
    )


async def help_command(update, context):
    if not is_owner(update.effective_user):
        return

    await update.message.reply_text(
        "❓ <b>BlockWatcher Help</b>\n\n"
        "➕ Add Wallet — Register an Ethereum wallet.\n"
        "👛 My Wallet — View your wallet.\n"
        "🗑 Remove Wallet — Remove your wallet.\n"
        "📊 Status — Check monitor status.\n\n"
        "<b>Commands</b>\n"
        "/start — Open dashboard\n"
        "/add — Add wallet\n"
        "/remove — Remove wallet\n"
        "/list — View wallet\n"
        "/status — Check status\n"
        "/help — Show help\n"
        "/cancel — Cancel operation",
        parse_mode="HTML",
        reply_markup=KEYBOARD,
    )


async def handle_text(update, context):
    if not is_owner(update.effective_user):
        return

    text = update.message.text.strip()

    if context.user_data.get("awaiting_wallet"):
        await process_wallet(update, context)
        return

    actions = {
        "➕ Add Wallet": add_wallet_start,
        "👛 My Wallet": my_wallet,
        "🗑 Remove Wallet": remove_wallet_start,
        "📊 Status": status,
        "❓ Help": help_command,
    }

    action = actions.get(text)

    if action:
        await action(update, context)
    else:
        await update.message.reply_text(
            "Please choose an option from the dashboard.",
            reply_markup=KEYBOARD,
        )


async def start_monitor(application):
    application.bot_data["owner_id"] = OWNER_ID

    application.bot_data["monitor_task"] = asyncio.create_task(
        monitor_loop(application)
    )


async def stop_monitor(application):
    task = application.bot_data.get("monitor_task")

    if task:
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass


def build_application():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(start_monitor)
        .post_shutdown(stop_monitor)
        .build()
    )

    app.bot_data["owner_id"] = OWNER_ID

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_wallet_start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("remove", remove_wallet_start))
    app.add_handler(CommandHandler("list", my_wallet))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_command))

    app.add_handler(CallbackQueryHandler(remove_callback))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text,
        )
    )

    return app
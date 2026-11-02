
import asyncio
import html
import json
import logging

import aiohttp
import websockets

from config import ALCHEMY_HTTPS_URL, ALCHEMY_WSS_URL
from database import (
    get_wallet,
    get_checkpoint,
    set_checkpoint,
    is_processed,
    mark_processed,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 8
HTTPS_FALLBACK_INTERVAL = 30
BLOCK_BATCH_SIZE = 100
CONFIRMATION_BUFFER = 3

RECONNECT_INITIAL_DELAY = 2
RECONNECT_MAX_DELAY = 60

CATEGORIES = [
    "external",
    "internal",
    "erc20",
    "erc721",
    "erc1155",
    "specialnft",
]


class AlchemyClient:
    def __init__(self, session):
        self.session = session
        self.request_id = 1

    async def rpc(self, method, params):
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }

        self.request_id += 1

        async with self.session.post(
            ALCHEMY_HTTPS_URL,
            json=payload,
        ) as response:
            response.raise_for_status()
            data = await response.json()

        if "error" in data:
            raise RuntimeError(
                f"Alchemy RPC error: {data['error']}"
            )

        return data["result"]

    async def get_latest_block(self):
        result = await self.rpc("eth_blockNumber", [])
        return int(result, 16)

    async def get_transfers(
        self,
        wallet,
        from_block,
        to_block,
        direction,
    ):
        transfers = []
        page_key = None

        while True:
            params = {
                "fromBlock": hex(from_block),
                "toBlock": hex(to_block),
                "category": CATEGORIES,
                "excludeZeroValue": True,
                "withMetadata": True,
                "maxCount": "0x3e8",
                "order": "asc",
            }

            if direction == "in":
                params["toAddress"] = wallet
            else:
                params["fromAddress"] = wallet

            if page_key:
                params["pageKey"] = page_key

            result = await self.rpc(
                "alchemy_getAssetTransfers",
                [params],
            )

            transfers.extend(
                result.get("transfers", [])
            )

            page_key = result.get("pageKey")

            if not page_key:
                break

        return transfers


def get_transfer_id(transfer):
    unique_id = transfer.get("uniqueId")

    if unique_id:
        return unique_id

    return "|".join([
        str(transfer.get("hash", "")),
        str(transfer.get("from", "")),
        str(transfer.get("to", "")),
        str(transfer.get("value", "")),
        str(transfer.get("category", "")),
        str(transfer.get("asset", "")),
        str(transfer.get("tokenId", "")),
    ])


def block_number(transfer):
    value = transfer.get("blockNum", "0x0")

    if isinstance(value, str):
        return int(value, 16)

    return int(value)


def format_amount(transfer):
    category = transfer.get("category", "")
    value = transfer.get("value")
    asset = transfer.get("asset")

    if category in ("external", "internal"):
        if value is None:
            return "Unknown ETH amount"

        return f"{float(value):g} ETH"

    if category == "erc20":
        if value is None:
            return html.escape(str(asset or "ERC-20"))

        return (
            f"{float(value):g} "
            f"{html.escape(str(asset or 'Token'))}"
        )

    if category in ("erc721", "erc1155", "specialnft"):
        token_id = transfer.get("tokenId")

        if token_id is not None:
            return (
                f"{html.escape(str(asset or 'NFT'))} "
                f"(Token ID: {html.escape(str(token_id))})"
            )

        return html.escape(str(asset or "NFT"))

    return html.escape(
        str(asset or category or "Transfer")
    )


def make_notification(transfer, wallet):
    sender = transfer.get("from") or "Unknown"
    receiver = transfer.get("to") or "Unknown"
    category = transfer.get("category", "unknown")
    tx_hash = transfer.get("hash", "")

    sender = html.escape(str(sender))
    receiver = html.escape(str(receiver))
    category_text = html.escape(str(category).upper())

    amount = format_amount(transfer)

    if sender.lower() == wallet.lower():
        direction = "OUTGOING"
        emoji = "📤"
    else:
        direction = "INCOMING"
        emoji = "📥"

    message = (
        f"{emoji} <b>{direction} TRANSFER</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Amount:</b> {amount}\n"
        f"📦 <b>Type:</b> {category_text}\n"
        f"📤 <b>From:</b> <code>{sender}</code>\n"
        f"📥 <b>To:</b> <code>{receiver}</code>\n"
    )

    if tx_hash:
        safe_hash = html.escape(str(tx_hash))

        message += (
            f"\n🔎 <a href=\"https://etherscan.io/tx/"
            f"{safe_hash}\">View on Etherscan</a>"
        )

    return message


async def scan_wallet(
    application,
    client,
    wallet,
    owner_id,
):
    latest_block = await client.get_latest_block()

    safe_latest_block = max(
        0,
        latest_block - CONFIRMATION_BUFFER,
    )

    checkpoint = get_checkpoint()

    if checkpoint is None:
        set_checkpoint(safe_latest_block)

        logger.info(
            "Monitoring baseline established at block %s",
            safe_latest_block,
        )
        return

    if safe_latest_block <= checkpoint:
        return

    start_block = checkpoint + 1

    while start_block <= safe_latest_block:
        end_block = min(
            start_block + BLOCK_BATCH_SIZE - 1,
            safe_latest_block,
        )

        incoming = await client.get_transfers(
            wallet,
            start_block,
            end_block,
            "in",
        )

        outgoing = await client.get_transfers(
            wallet,
            start_block,
            end_block,
            "out",
        )

        combined = {}

        for transfer in incoming + outgoing:
            transfer_id = get_transfer_id(transfer)
            category = transfer.get(
                "category",
                "unknown",
            )

            combined[(transfer_id, category)] = transfer

        transfers = sorted(
            combined.values(),
            key=block_number,
        )

        for transfer in transfers:
            transfer_id = get_transfer_id(transfer)
            category = transfer.get(
                "category",
                "unknown",
            )

            if is_processed(transfer_id, category):
                continue

            message = make_notification(
                transfer,
                wallet,
            )

            await application.bot.send_message(
                chat_id=owner_id,
                text=message,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )

            mark_processed(
                transfer_id,
                category,
            )

            logger.info(
                "Transfer notification sent: %s",
                transfer_id,
            )

        set_checkpoint(end_block)

        logger.info(
            "Scanned blocks %s to %s",
            start_block,
            end_block,
        )

        start_block = end_block + 1


async def websocket_listener(trigger_event, state):
    reconnect_delay = RECONNECT_INITIAL_DELAY

    while True:
        try:
            logger.info(
                "Connecting to Alchemy WebSocket..."
            )

            async with websockets.connect(
                ALCHEMY_WSS_URL,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
                open_timeout=20,
                max_size=2**20,
            ) as websocket:

                await websocket.send(
                    json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "eth_subscribe",
                        "params": ["newHeads"],
                    })
                )

                response = json.loads(
                    await websocket.recv()
                )

                if response.get("error"):
                    raise RuntimeError(
                        f"WebSocket subscription error: "
                        f"{response['error']}"
                    )

                if "result" not in response:
                    raise RuntimeError(
                        "Invalid WebSocket subscription response"
                    )

                state["ws_connected"] = True
                reconnect_delay = RECONNECT_INITIAL_DELAY

                logger.info(
                    "Alchemy WebSocket connected. "
                    "Subscribed to new Ethereum blocks."
                )

                async for raw_message in websocket:
                    message = json.loads(raw_message)

                    if (
                        message.get("method")
                        == "eth_subscription"
                    ):
                        trigger_event.set()

        except asyncio.CancelledError:
            raise

        except Exception:
            logger.exception(
                "WebSocket disconnected."
            )

        finally:
            state["ws_connected"] = False

        logger.warning(
            "WebSocket reconnecting in %s seconds...",
            reconnect_delay,
        )

        await asyncio.sleep(reconnect_delay)

        reconnect_delay = min(
            reconnect_delay * 2,
            RECONNECT_MAX_DELAY,
        )


async def monitor_loop(application):
    logger.info(
        "Ethereum monitor started."
    )

    timeout = aiohttp.ClientTimeout(total=30)

    trigger_event = asyncio.Event()

    state = {
        "ws_connected": False,
    }

    websocket_task = None

    try:
        async with aiohttp.ClientSession(
            timeout=timeout,
        ) as session:

            client = AlchemyClient(session)

            websocket_task = asyncio.create_task(
                websocket_listener(
                    trigger_event,
                    state,
                )
            )

            while True:
                interval = (
                    HTTPS_FALLBACK_INTERVAL
                    if state["ws_connected"]
                    else POLL_INTERVAL
                )

                try:
                    await asyncio.wait_for(
                        trigger_event.wait(),
                        timeout=interval,
                    )

                except asyncio.TimeoutError:
                    pass

                trigger_event.clear()

                wallet = get_wallet()

                if not wallet:
                    continue

                owner_id = application.bot_data.get(
                    "owner_id"
                )

                if not owner_id:
                    logger.error(
                        "Telegram owner ID is missing."
                    )
                    continue

                try:
                    await scan_wallet(
                        application,
                        client,
                        wallet,
                        owner_id,
                    )

                except asyncio.CancelledError:
                    raise

                except Exception:
                    logger.exception(
                        "Ethereum monitoring error."
                    )

    except asyncio.CancelledError:
        logger.info(
            "Ethereum monitor stopped."
        )
        raise

    finally:
        if websocket_task:
            websocket_task.cancel()

            try:
                await websocket_task
            except asyncio.CancelledError:
                pass

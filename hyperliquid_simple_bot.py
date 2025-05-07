import os
import time
import logging
from eth_account import Account # Part of eth-account, often installed with web3py
from eth_account.signers.local import LocalAccount # Correct import path
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

# --- Configuration & Security ---

# **NEVER HARDCODE PRIVATE KEYS** - Use environment variables or a secure config manager
# Set this environment variable before running: export HL_TESTNET_KEY="0xyour_private_key"
TESTNET_PRIVATE_KEY = os.environ.get("HL_TESTNET_KEY") 
TESTNET_RPC_URL = constants.TESTNET_API_URL # Use SDK constant for Testnet URL

# Check if the private key is loaded
if not TESTNET_PRIVATE_KEY:
    raise ValueError("HL_TESTNET_KEY environment variable not set. Exiting for safety.")
if not TESTNET_PRIVATE_KEY.startswith("0x"):
     TESTNET_PRIVATE_KEY = "0x" + TESTNET_PRIVATE_KEY # Ensure hex prefix

# Create account object from private key
try:
    ACCOUNT: LocalAccount = Account.from_key(TESTNET_PRIVATE_KEY)
    TESTNET_WALLET_ADDRESS = ACCOUNT.address
    print(f"Loaded Testnet account: {TESTNET_WALLET_ADDRESS}")
except Exception as e:
    print(f"Error loading private key: {e}. Ensure it's a valid 64-char hex key.")
    exit()


# Bot Parameters
ASSET_SYMBOL = "BTC" # Asset to trade
ORDER_SIZE_BTC = 0.0001 # Keep this VERY small on testnet
PRICE_OFFSET_USD = 10.0 # Place buy order $10 below mid-price
ORDER_TYPE = "limit" # We want a limit order
TIME_IN_FORCE = "Gtc" # Good Til Canceled (standard for limit)
SLIPPAGE_TOLERANCE = 0.01 # Example: 1% (More relevant for market orders, but good practice)

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Helper Functions ---

def get_market_mid_price(info_client: Info, asset: str) -> float | None:
    """Fetches the order book and calculates the mid-price."""
    logging.info(f"Fetching order book for {asset}...")
    try:
        order_book = info_client.order_book(asset)
        if order_book and order_book.get('levels') and len(order_book['levels']) >= 2:
            # Levels are typically [bid_levels, ask_levels]
            best_bid = float(order_book['levels'][0][0]['px']) # First bid level, price
            best_ask = float(order_book['levels'][1][0]['px']) # First ask level, price
            mid_price = (best_bid + best_ask) / 2
            logging.info(f"Best Bid: {best_bid}, Best Ask: {best_ask}, Mid Price: {mid_price}")
            return mid_price
        else:
            logging.warning("Order book data incomplete or missing levels.")
            return None
    except Exception as e:
        logging.error(f"Error fetching or parsing order book for {asset}: {e}")
        return None

def place_limit_order(exchange_client: Exchange, asset: str, side: str, size: float, limit_px: float):
    """Places a limit order using the Exchange client."""
    logging.info(f"Attempting to place {side} order: {size} {asset} @ {limit_px:.2f}")
    try:
        # SDK's order function likely takes asset index, check SDK examples/docs
        # For simplicity, assuming SDK handles symbol mapping or direct symbol use
        # The vaultAddress=None might be needed depending on SDK version/context
        order_result = exchange_client.order(
            asset, 
            is_buy=(side == "buy"), 
            sz=size, 
            limit_px=limit_px, 
            order_type={"limit": {"tif": TIME_IN_FORCE}},
            # cloid=None # Optional client order ID
        )
        logging.info(f"Order placement result: {order_result}")

        # Check response structure based on SDK docs/examples
        if order_result and order_result.get("status") == "ok":
            # Extract the order ID (oid) - structure might vary!
            statuses = order_result.get("response", {}).get("data", {}).get("statuses", [])
            if statuses and isinstance(statuses[0], dict) and "resting" in statuses[0]:
                 oid = statuses[0]["resting"]["oid"]
                 logging.info(f"Successfully placed order with OID: {oid}")
                 return oid
            elif statuses and isinstance(statuses[0], dict) and "filled" in statuses[0]:
                 logging.info("Order filled immediately upon placement.")
                 # May not get a resting OID if fully filled instantly
                 return None # Indicate it didn't rest
            else:
                 logging.warning("Order placed but couldn't extract resting OID from response.")
                 return None
        else:
            logging.error(f"Order placement failed or status not 'ok'. Response: {order_result}")
            return None
            
    except Exception as e:
        logging.error(f"Exception during order placement: {e}")
        return None

def get_order_status(info_client: Info, user_address: str, oid: int) -> dict | None:
    """Queries the status of a specific order by OID."""
    logging.info(f"Querying status for order OID: {oid}")
    try:
        # Need to find the correct function in SDK - might be part of user_state or a specific query
        # Hypothetical function name, replace with actual SDK function:
        order_data = info_client.query_order_by_oid(user_address, oid) 
        # Or might need to iterate through info_client.open_orders(user_address)
        
        if order_data:
            logging.info(f"Order OID {oid} status data: {order_data}")
            # Return the relevant part of the status (structure depends on SDK)
            return order_data # Adjust based on actual return structure
        else:
            logging.warning(f"Could not find status for order OID: {oid}. It might be filled or canceled.")
            return None
    except Exception as e:
        logging.error(f"Exception querying order status for OID {oid}: {e}")
        return None
        
def cancel_order(exchange_client: Exchange, asset: str, oid: int):
    """Cancels an order using its OID."""
    logging.info(f"Attempting to cancel order OID: {oid} for asset {asset}")
    try:
        # Assuming asset symbol is needed along with OID
        cancel_result = exchange_client.cancel(asset, oid)
        logging.info(f"Cancellation result for OID {oid}: {cancel_result}")
        
        # Check response structure based on SDK docs/examples
        if cancel_result and cancel_result.get("status") == "ok":
            logging.info(f"Successfully submitted cancellation for OID: {oid}")
            return True
        else:
            logging.error(f"Cancellation failed or status not 'ok' for OID {oid}. Response: {cancel_result}")
            return False
            
    except Exception as e:
        logging.error(f"Exception during order cancellation for OID {oid}: {e}")
        return False

# --- Main Bot Logic ---
def main():
    logging.info("--- Starting Simple Hyperliquid Bot (Testnet) ---")
    
    # Initialize SDK clients
    try:
        info = Info(constants.TESTNET_API_URL, skip_ws=True) # Skip WebSocket for this simple example
        # The Exchange client needs the signer (Account object)
        exchange = Exchange(ACCOUNT, constants.TESTNET_API_URL) 
        logging.info("Hyperliquid SDK clients initialized for Testnet.")
    except Exception as e:
        logging.error(f"Failed to initialize SDK clients: {e}")
        return

    # 1. Get Mid Price
    mid_price = get_market_mid_price(info, ASSET_SYMBOL)
    if mid_price is None:
        logging.error("Could not determine mid-price. Exiting.")
        return
        
    # 2. Calculate Limit Price & Define Order
    # Place a BUY order slightly below mid-price
    limit_buy_price = round(mid_price - PRICE_OFFSET_USD, 2) # Round to appropriate precision for BTC/USD
    order_side = "buy"
    
    # --- Strict Risk Check ---
    if limit_buy_price <= 0:
        logging.error(f"Calculated limit price ({limit_buy_price}) is zero or negative. Aborting.")
        return
    if ORDER_SIZE_BTC <= 0:
         logging.error(f"Order size ({ORDER_SIZE_BTC}) is zero or negative. Aborting.")
         return

    # 3. Place Order
    placed_order_id = place_limit_order(exchange, ASSET_SYMBOL, order_side, ORDER_SIZE_BTC, limit_buy_price)

    # 4. Monitor & Cancel Logic
    if placed_order_id is not None:
        logging.info(f"Waiting a few seconds before checking/canceling order {placed_order_id}...")
        time.sleep(10) # Wait time

        # 5. Check Status (Optional but good practice)
        order_status = get_order_status(info, TESTNET_WALLET_ADDRESS, placed_order_id)
        # Log status if found, otherwise proceed to cancel anyway

        # 6. Attempt Cancellation
        cancel_success = cancel_order(exchange, ASSET_SYMBOL, placed_order_id)
        if cancel_success:
             logging.info(f"Order {placed_order_id} cancellation submitted successfully.")
        else:
             logging.warning(f"Could not confirm cancellation for order {placed_order_id}. Check manually.")
             
    elif placed_order_id is None and limit_buy_price is not None:
         # Handle case where order might have filled instantly or failed to place
         logging.info("Order did not receive a resting OID (might be filled instantly or failed). Checking open orders...")
         try:
             open_orders = info.open_orders(TESTNET_WALLET_ADDRESS)
             logging.info(f"Current open orders: {open_orders}")
             # Add logic here to see if an unexpected order matching parameters exists and try to cancel if needed
         except Exception as e:
             logging.error(f"Could not check open orders after placement: {e}")
             
    else:
        logging.error("Order placement failed. No OID received.")

    logging.info("--- Bot cycle finished ---")


if __name__ == "__main__":
    # --- Final Safety Check ---
    if constants.MAINNET_API_URL in TESTNET_RPC_URL:
         logging.error("CRITICAL ERROR: Attempting to use Mainnet URL in Testnet configuration!")
    elif "testnet" not in TESTNET_RPC_URL.lower():
         logging.warning("Warning: Configured RPC URL does not explicitly contain 'testnet'. Double-check it's correct.")
         # Add a confirmation step or exit if unsure
         # confirm = input(f"Using RPC URL: {TESTNET_RPC_URL}. Continue? (yes/no): ")
         # if confirm.lower() != 'yes':
         #     print("Exiting.")
         #     exit()
    else:
        main()
        
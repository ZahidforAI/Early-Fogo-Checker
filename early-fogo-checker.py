import streamlit as st
import asyncio
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import sys

# Fogo testnet configuration
FOGO_RPC_URL = "https://testnet.fogo.io"
TESTNET_LAUNCH_DATE = datetime(2025, 7, 22, tzinfo=timezone.utc)

# Updated tiers based on Fogo testnet timeline (launched July 22, 2025)
TIERS = [
    (2_200_000, "🔥 Genesis Early (Day 1)"),
    (4_300_000, "🟠 Super Early (Day 2)"),
    (6_500_000, "🟡 Early (Day 3)"),
    (10_800_000, "🟤 Late (Day 5)"),
    (float("inf"), "🔴 Recently Joined")
]

class FogoTestnetChecker:
    def __init__(self):
        self.client = AsyncClient(FOGO_RPC_URL)
    
    async def close(self):
        try:
            await self.client.close()
        except Exception as e:
            print(f"Error closing client: {e}")
    
    def is_valid_wallet_address(self, address: str) -> bool:
        """Validate if the provided string is a valid Solana wallet address"""
        try:
            if not address or len(address.strip()) == 0:
                return False
            Pubkey.from_string(address.strip())
            return True
        except Exception as e:
            print(f"Address validation error: {e}")
            return False
    
    async def get_account_info(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """Get account information from Fogo testnet"""
        try:
            pubkey = Pubkey.from_string(wallet_address.strip())
            response = await self.client.get_account_info(pubkey, commitment=Confirmed)
            return response
        except Exception as e:
            print(f"Error getting account info: {e}")
            return None
    
    async def get_transaction_history(self, wallet_address: str, limit: int = 1000) -> list:
        """Get transaction history for the wallet"""
        try:
            pubkey = Pubkey.from_string(wallet_address.strip())
            response = await self.client.get_signatures_for_address(
                pubkey, 
                limit=limit,
                commitment=Confirmed
            )
            if response and hasattr(response, 'value') and response.value:
                # Sort by slot number to get the earliest transaction first
                sorted_txs = sorted(response.value, key=lambda x: x.slot if x.slot else float('inf'))
                return sorted_txs
            return []
        except Exception as e:
            print(f"Error fetching transaction history: {e}")
            return []
    
    async def get_latest_slot(self) -> Optional[int]:
        """Get the latest slot number"""
        try:
            response = await self.client.get_slot(commitment=Confirmed)
            if response and hasattr(response, 'value'):
                return response.value
            return None
        except Exception as e:
            print(f"Error getting latest slot: {e}")
            return None
    
    def calculate_score(self, first_slot: int, latest_slot: int) -> float:
        """Calculate early score based on slot numbers"""
        try:
            if latest_slot <= first_slot or latest_slot <= 0:
                return 0.0
            
            # Calculate early ratio
            early_ratio = 1 - (first_slot / latest_slot)
            base_score = early_ratio * 100
            
            # Day-based scoring for testnet
            slots_per_day = 2_160_000  # ~40ms blocks
            
            if first_slot < slots_per_day:  # Day 1 users
                score = min(base_score + 40, 99.9)
            elif first_slot < slots_per_day * 2:  # Day 2 users
                score = min(base_score + 30, 95.0)
            elif first_slot < slots_per_day * 3:  # Day 3 users
                score = min(base_score + 20, 90.0)
            elif first_slot < slots_per_day * 5:  # Day 5 users
                score = min(base_score + 10, 85.0)
            else:
                score = max(base_score, 50.0)
            
            return round(max(score, 0.0), 2)
        except Exception as e:
            print(f"Error calculating score: {e}")
            return 0.0
    
    def get_tier(self, slot_num: int) -> str:
        """Get tier based on slot number"""
        try:
            for threshold, label in TIERS:
                if slot_num < threshold:
                    return label
            return "🔴 Unknown"
        except Exception:
            return "🔴 Unknown"
    
    async def check_wallet(self, wallet_address: str) -> Dict[str, Any]:
        """Check wallet on Fogo testnet"""
        result = {
            'valid': False,
            'exists': False,
            'first_slot': None,
            'join_date': None,
            'score': None,
            'tier': None,
            'error': None
        }
        
        try:
            # Validate wallet address
            if not self.is_valid_wallet_address(wallet_address):
                result['error'] = "Invalid wallet address format"
                return result
            
            result['valid'] = True
            
            # Check if account exists
            account_info = await self.get_account_info(wallet_address)
            if not account_info or not hasattr(account_info, 'value') or not account_info.value:
                result['error'] = "Wallet not found on Fogo testnet"
                return result
            
            result['exists'] = True
            
            # Get transaction history
            transactions = await self.get_transaction_history(wallet_address)
            if not transactions:
                result['error'] = "No transaction history found"
                return result
            
            # Get the first transaction
            first_tx = transactions[0] if transactions else None
            if not first_tx or not hasattr(first_tx, 'slot') or not first_tx.slot:
                result['error'] = "No valid first transaction found"
                return result
            
            result['first_slot'] = first_tx.slot
            
            # Convert slot to date
            if hasattr(first_tx, 'block_time') and first_tx.block_time:
                result['join_date'] = datetime.fromtimestamp(first_tx.block_time, tz=timezone.utc).date()
            else:
                # Estimate based on slot number
                estimated_seconds = (first_tx.slot * 0.04)  # 40ms per block
                estimated_date = TESTNET_LAUNCH_DATE + timedelta(seconds=estimated_seconds)
                result['join_date'] = estimated_date.date()
            
            # Calculate score and tier
            latest_slot = await self.get_latest_slot()
            if latest_slot and result['first_slot']:
                result['score'] = self.calculate_score(result['first_slot'], latest_slot)
                result['tier'] = self.get_tier(result['first_slot'])
            else:
                result['error'] = "Could not calculate score"
            
        except Exception as e:
            result['error'] = f"Unexpected error: {str(e)}"
            print(f"Unexpected error in check_wallet: {e}")
        
        return result

# Helper function to run async code in Streamlit
def run_async_check(wallet_address: str) -> Dict[str, Any]:
    """Run async wallet check in a way that works with Streamlit"""
    try:
        # Check if we're in an existing event loop
        try:
            loop = asyncio.get_running_loop()
            # If we're in a running loop, we need to use a different approach
            import concurrent.futures
            import threading
            
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    checker = FogoTestnetChecker()
                    result = new_loop.run_until_complete(checker.check_wallet(wallet_address))
                    new_loop.run_until_complete(checker.close())
                    return result
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result(timeout=30)  # 30 second timeout
                
        except RuntimeError:
            # No running loop, we can create our own
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                checker = FogoTestnetChecker()
                result = loop.run_until_complete(checker.check_wallet(wallet_address))
                loop.run_until_complete(checker.close())
                return result
            finally:
                loop.close()
                
    except Exception as e:
        return {
            'valid': False,
            'exists': False,
            'first_slot': None,
            'join_date': None,
            'score': None,
            'tier': None,
            'error': f"System error: {str(e)}"
        }

# Streamlit App Configuration
st.set_page_config(
    page_title="Fogo Early Checker", 
    page_icon="🔥", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

# CSS Styling (keeping your original styling)
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    .stApp {
        background: linear-gradient(135deg, #FF8C00 0%, #FFA500 50%, #FFB347 100%);
        color: white;
        font-family: 'Inter', sans-serif;
    }

    .block-container {
        max-width: 600px;
        width: 90%;
        padding: 1.5rem;
        background-color: rgba(255, 255, 255, 0.95);
        border-radius: 15px;
        box-shadow: 0 8px 20px rgba(0, 0, 0, 0.15);
        color: #1F2937;
        animation: fadeIn 0.5s ease-in-out;
        margin: 2rem auto;
    }

    @keyframes fadeIn {
        0% { opacity: 0; transform: translateY(10px); }
        100% { opacity: 1; transform: translateY(0); }
    }

    .title {
        color: #FF8C00;
        font-size: clamp(2rem, 5vw, 3rem);
        font-weight: 800;
        margin-bottom: 0.5rem;
        text-align: center;
    }

    .subtitle {
        color: #CC7000;
        font-size: clamp(0.9rem, 3vw, 1rem);
        margin-bottom: 1.5rem;
        text-align: center;
    }

    .stButton > button {
        background-color: #FF8C00;
        color: white;
        border-radius: 10px;
        font-weight: 600;
        padding: 0.75rem 1.5rem;
        border: none;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        width: 100%;
    }

    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 10px rgba(255, 140, 0, 0.3);
    }

    .result-box {
        font-size: clamp(1.8rem, 5vw, 2.5rem);
        font-weight: 800;
        color: #FF8C00;
        margin-top: 1rem;
        text-align: center;
    }

    .info-text {
        font-size: clamp(0.95rem, 3vw, 1.1rem);
        font-weight: 500;
        color: #CC7000;
        margin: 0.5rem 0;
        text-align: center;
    }

    footer {
        text-align: center;
        margin-top: 1rem;
        color: #CC7000;
    }

    footer a {
        color: #FF8C00;
        text-decoration: none;
    }
    </style>
""", unsafe_allow_html=True)

# Main UI
st.markdown('<h2 class="title">🔥 EARLY FOGO CHECKER</h2>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Check how early your wallet joined the Fogo Testnet!</p>', unsafe_allow_html=True)

wallet = st.text_input("Wallet Address", placeholder="Enter Solana wallet address...")
check_button = st.button("🔥 Check Wallet")

if check_button:
    if wallet and wallet.strip():
        with st.spinner("🔥 Checking wallet..."):
            result = run_async_check(wallet.strip())
        
        if result.get('error'):
            st.error(f"❌ {result['error']}")
        elif not result['valid']:
            st.error("❌ Invalid wallet address format.")
        elif not result['exists']:
            st.error("❌ Wallet not found on Fogo testnet.")
        else:
            if result['first_slot'] and result['join_date'] and result['score'] is not None and result['tier']:
                st.markdown(f"<div class='info-text'>🎯 First TX Slot: <b>{result['first_slot']:,}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='info-text'>📅 First TX Date: <b>{result['join_date']}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='info-text'>🏆 Tier: <b>{result['tier']}</b></div>", unsafe_allow_html=True)
                st.markdown(f"<div class='result-box'>Early Score: {result['score']}%</div>", unsafe_allow_html=True)
                st.markdown(f"<div style='color:#CC7000; font-weight:600; text-align:center;'>🔥 You're earlier than ~{int(result['score'])}% of wallets!</div>", unsafe_allow_html=True)
            else:
                st.success("✅ Wallet exists on Fogo testnet")
                st.info("ℹ️ No transaction history found or unable to calculate score.")
    else:
        st.warning("⚠️ Please enter a wallet address.")

st.markdown("""
    <footer>
        Made with 🧡 by <a href="https://x.com/0xPAF" target="_blank">PAF</a>
    </footer>
""", unsafe_allow_html=True)

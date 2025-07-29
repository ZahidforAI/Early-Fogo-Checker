import streamlit as st
import asyncio
from solders.pubkey import Pubkey
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

# Fogo testnet configuration
FOGO_RPC_URL = "https://testnet.fogo.io"
TESTNET_LAUNCH_DATE = datetime(2025, 7, 22, tzinfo=timezone.utc)

# Updated tiers based on Fogo testnet timeline (launched July 22, 2025)
# With ~40ms block times, in 6 days we have roughly:
# - Day 1: ~2.2M slots
# - Day 2: ~4.3M slots  
# - Day 3: ~6.5M slots
# - Day 6 (today): ~13M slots
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
        await self.client.close()
    
    def is_valid_wallet_address(self, address: str) -> bool:
        """Validate if the provided string is a valid Solana wallet address"""
        try:
            Pubkey.from_string(address)
            return True
        except Exception:
            return False
    
    async def get_account_info(self, wallet_address: str) -> Optional[Dict[str, Any]]:
        """Get account information from Fogo testnet"""
        try:
            pubkey = Pubkey.from_string(wallet_address)
            response = await self.client.get_account_info(pubkey, commitment=Confirmed)
            return response
        except Exception:
            return None
    
    async def get_transaction_history(self, wallet_address: str, limit: int = 1000) -> list:
        """Get transaction history for the wallet"""
        try:
            pubkey = Pubkey.from_string(wallet_address)
            # Get all transactions, sorted by oldest first
            response = await self.client.get_signatures_for_address(
                pubkey, 
                limit=limit,
                commitment=Confirmed
            )
            if response.value:
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
            return response.value if response else None
        except Exception:
            return None
    
    def calculate_score(self, first_slot: int, latest_slot: int) -> float:
        """Calculate early score based on slot numbers - Fogo launched July 22, 2025"""
        print(f"Debug - First slot: {first_slot}, Latest slot: {latest_slot}")
        
        if latest_slot <= first_slot:
            return 0.0
        
        # Since testnet is only 6 days old, anyone with transactions should have high scores
        early_ratio = 1 - (first_slot / latest_slot)
        base_score = early_ratio * 100
        
        print(f"Debug - Early ratio: {early_ratio}, Base score: {base_score}")
        
        # Day-based scoring for super fresh testnet (launched July 22, 2025)
        days_since_launch = (datetime.now(timezone.utc) - TESTNET_LAUNCH_DATE).days
        slots_per_day = 2_160_000  # ~40ms blocks = 25 blocks/sec * 86400 sec/day
        
        if first_slot < slots_per_day:  # Day 1 users
            score = min(base_score + 40, 99.9)  # Huge bonus for day 1
        elif first_slot < slots_per_day * 2:  # Day 2 users
            score = min(base_score + 30, 95.0)  # Big bonus for day 2
        elif first_slot < slots_per_day * 3:  # Day 3 users
            score = min(base_score + 20, 90.0)  # Good bonus for day 3
        elif first_slot < slots_per_day * 5:  # Day 5 users
            score = min(base_score + 10, 85.0)  # Small bonus
        else:
            score = max(base_score, 50.0)  # Even recent users get decent score since testnet is so new
        
        print(f"Debug - Final score: {score}")
        return round(score, 2)
    
    def get_tier(self, slot_num: int) -> str:
        """Get tier based on slot number"""
        for threshold, label in TIERS:
            if slot_num < threshold:
                return label
        return "🔴 Unknown"
    
    async def check_wallet(self, wallet_address: str) -> Dict[str, Any]:
        """Check wallet on Fogo testnet"""
        result = {
            'valid': False,
            'exists': False,
            'first_slot': None,
            'join_date': None,
            'score': None,
            'tier': None
        }
        
        # Validate wallet address
        if not self.is_valid_wallet_address(wallet_address):
            return result
        
        result['valid'] = True
        
        # Check if account exists
        account_info = await self.get_account_info(wallet_address)
        if not account_info or not account_info.value:
            return result
        
        result['exists'] = True
        
        # Get transaction history and find the FIRST (earliest) transaction
        transactions = await self.get_transaction_history(wallet_address)
        if not transactions:
            print("Debug - No transactions found")
            return result
        
        print(f"Debug - Found {len(transactions)} transactions")
        
        # Get the first transaction (should be sorted by slot already)
        first_tx = transactions[0] if transactions else None
        if not first_tx or not first_tx.slot:
            print("Debug - No valid first transaction found")
            return result
        
        print(f"Debug - First transaction slot: {first_tx.slot}")
        result['first_slot'] = first_tx.slot
        
        # Convert slot to date based on July 22, 2025 launch
        if first_tx.block_time:
            result['join_date'] = datetime.fromtimestamp(first_tx.block_time, tz=timezone.utc).date()
        else:
            # Estimate based on slot number and 40ms block time from launch date
            estimated_seconds = (first_tx.slot * 0.04)  # 40ms per block
            estimated_date = TESTNET_LAUNCH_DATE + timedelta(seconds=estimated_seconds)
            result['join_date'] = estimated_date.date()
        
        # Calculate score and tier
        latest_slot = await self.get_latest_slot()
        print(f"Debug - Latest slot from RPC: {latest_slot}")
        
        if latest_slot and result['first_slot']:
            result['score'] = self.calculate_score(result['first_slot'], latest_slot)
            result['tier'] = self.get_tier(result['first_slot'])
        else:
            print("Debug - Could not get latest slot or first slot missing")
        
        return result

# Streamlit App
st.set_page_config(page_title="Fogo Early Checker", page_icon="🔥", layout="centered")

# CSS Styling
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    .stApp {
        background: linear-gradient(135deg, #FF8C00 0%, #FFA500 50%, #FFB347 100%);
        color: white;
        font-family: 'Inter', sans-serif;
        display: flex;
        justify-content: center;
        align-items: center;
        min-height: 100vh;
        margin: 0;
        padding: 0;
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
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        margin: 7rem auto;
        transform: none;
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
        display: inline-block;
        --orange: #FF8C00;
        --glow-orange: #FFA500;
        --speed: 1200ms;
        animation: breath calc(var(--speed)) ease calc(var(--index, 0) * 100ms) infinite alternate;
    }

    @keyframes breath {
        from {
            animation-timing-function: ease-out;
            transform: scale(1);
            text-shadow: none;
        }
        to {
            transform: scale(1.25) translateY(-5px) perspective(1px);
            text-shadow: 0 0 20px var(--glow-orange);
            animation-timing-function: ease-in-out;
        }
    }

    .subtitle {
        color: #CC7000;
        font-size: clamp(0.9rem, 3vw, 1rem);
        margin-bottom: 1.5rem;
    }

    section[data-testid="stTextInput"] {
        width: 100%;
        display: flex;
        justify-content: center;
        flex-direction: column;
        align-items: center;
    }

    section[data-testid="stTextInput"] > div {
        width: 100%;
        max-width: 400px;
    }

    section[data-testid="stTextInput"] > div > div {
        width: 100%;
    }

    section[data-testid="stTextInput"] > div > div > input {
        background-color: #F9FAFB;
        color: #FF8C00;
        border-radius: 10px;
        padding: 0.75rem;
        font-size: 1rem;
        border: 1px solid #E5E7EB;
        width: 100%;
        box-sizing: border-box;
        transition: border-color 0.3s ease;
    }

    section[data-testid="stTextInput"] label {
        display: block;
        margin-bottom: 0.5rem;
        font-weight: 600;
        color: #FF8C00;
        text-align: left;
        width: 100%;
        max-width: 400px;
    }

    .stButton > button {
        background-color: #FF8C00;
        color: white;
        border-radius: 10px;
        font-weight: 600;
        padding: 0.75rem 1.5rem;
        border: none;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        display: block;
        margin: 1rem auto 0;
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
        animation: popIn 0.3s ease;
    }

    @keyframes popIn {
        0% { transform: scale(0.95); opacity: 0; }
        100% { transform: scale(1); opacity: 1; }
    }

    .info-text {
        font-size: clamp(0.95rem, 3vw, 1.1rem);
        font-weight: 500;
        color: #CC7000;
        margin: 0.5rem 0;
    }

    .loading-spinner {
        border: 4px solid #E5E7EB;
        border-top: 4px solid #FF8C00;
        border-radius: 50%;
        width: 40px;
        height: 40px;
        animation: spin 1s linear infinite;
        margin: 1rem auto;
    }

    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }

    /* Mobile responsiveness */
    @media screen and (max-width: 600px) {
        .block-container {
            width: 95%;
            padding: 1rem;
            margin: 1rem auto;
            transform: translateY(5%);
        }
        .title {
            font-size: clamp(1.5rem, 4vw, 2rem);
        }
        .result-box {
            font-size: clamp(1.5rem, 4vw, 2rem);
        }
    }
    </style>
""", unsafe_allow_html=True)

# Main UI
with st.container():
    st.markdown('<h2 class="title">🔥 EARLY FOGO CHECKER</h2>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Check how early your wallet joined the Fogo Testnet!</p>', unsafe_allow_html=True)
    st.markdown("""
    <footer>
        Made with 🧡 by <a href="https://x.com/0xPAF" target="_blank">PAF</a>
    </footer>
""", unsafe_allow_html=True)

    wallet = st.text_input("Wallet Address", placeholder="Enter Solana wallet address...")
    check_button = st.button("🔥 Check Wallet")

    if check_button:
        if wallet:
            spinner_placeholder = st.empty()
            spinner_placeholder.markdown('<div class="loading-spinner"></div>', unsafe_allow_html=True)
            
            checker = FogoTestnetChecker()
            
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(checker.check_wallet(wallet))
                loop.run_until_complete(checker.close())
                loop.close()
            except Exception as e:
                spinner_placeholder.empty()
                st.error(f"❌ Error checking wallet: {str(e)}")
                st.stop()
            
            spinner_placeholder.empty()
            
            if not result['valid']:
                st.error("❌ Invalid wallet address format.")
            elif not result['exists']:
                st.error("❌ Wallet not found on Fogo testnet.")
            else:
                if result['first_slot'] and result['join_date'] and result['score'] and result['tier']:
                    st.markdown(f"<div class='info-text'>🎯 First TX Slot: <b>{result['first_slot']:,}</b></div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='info-text'>📅 First TX Date: <b>{result['join_date']}</b></div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='info-text'>🏆 Tier: <b>{result['tier']}</b></div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='result-box'>Early Score: {result['score']}%</div>", unsafe_allow_html=True)
                    st.markdown(f"<div style='color:#CC7000; font-weight:600;'>🔥 You're earlier than ~{int(result['score'])}% of wallets!</div>", unsafe_allow_html=True)
                else:
                    st.success("✅ Wallet exists on Fogo testnet")
                    st.info("ℹ️ No transaction history found or unable to calculate score.")
        else:
            st.warning("⚠️ Please enter a wallet address.")

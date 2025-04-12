import asyncio
import websockets
import json
import pandas as pd
import numpy as np
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from threading import Thread

app = FastAPI()
latest_signal = {
    "timestamp": None,
    "signal": None,
    "price": None,
    "indicators": {
        "rsi": None,
        "macd": None,
        "macd_signal": None
    }
}

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=period).mean()
    avg_loss = pd.Series(loss).rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices, slow=26, fast=12, signal=9):
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    return macd, signal_line

async def btc_data_collector():
    uri = "wss://stream.binance.com:9443/ws/btcusdt@kline_1m"
    async with websockets.connect(uri) as websocket:
        closes = []

        while True:
            message = await websocket.recv()
            data = json.loads(message)
            kline = data['k']
            if kline['x']:
                close_price = float(kline['c'])
                closes.append(close_price)
                if len(closes) > 100:
                    closes = closes[-100:]

                prices = pd.Series(closes)
                rsi = calculate_rsi(prices).iloc[-1]
                macd, signal_line = calculate_macd(prices)
                macd_val = macd.iloc[-1]
                signal_val = signal_line.iloc[-1]

                signal = None
                if rsi < 30 and macd_val > signal_val:
                    signal = "BUY"
                elif rsi > 70 and macd_val < signal_val:
                    signal = "SELL"

                global latest_signal
                latest_signal = {
                    "timestamp": kline['T'],
                    "signal": signal,
                    "price": close_price,
                    "indicators": {
                        "rsi": round(rsi, 2),
                        "macd": round(macd_val, 2),
                        "macd_signal": round(signal_val, 2)
                    }
                }

@app.get("/signal")
async def get_signal():
    return JSONResponse(content=latest_signal)

def start_data_collector():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(btc_data_collector())

Thread(target=start_data_collector, daemon=True).start()
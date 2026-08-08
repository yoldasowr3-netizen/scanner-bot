import ccxt
import pandas as pd
import time
import requests
import json
import os
from datetime import datetime, timedelta
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import pandas_ta_classic as ta

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = "7591952058:AAGDDfxq6Tz_PHR25WG-0PsONySug4iQ1B0"
TELEGRAM_CHAT_ID = "6759712444"

TIMEFRAMES = ['1h', '4h', '1d']
RSI_PERIOD = 14
SMA_PERIOD = 14
VOLUME_MIN = 1_000_000
SIGNAL_COOLDOWN_HOURS = 24

SIGNAL_HISTORY_FILE = "signal_history.json"

# --- ИСТОРИЯ ---
def load_signal_history():
    try:
        if os.path.exists(SIGNAL_HISTORY_FILE):
            with open(SIGNAL_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_signal_history(history):
    try:
        with open(SIGNAL_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"❌ Ошибка сохранения: {e}")

def can_send_signal(symbol, timeframe):
    history = load_signal_history()
    key = f"{symbol}_{timeframe}"
    current_time = datetime.now()
    
    if key in history:
        last_signal_time = datetime.fromisoformat(history[key])
        time_diff = current_time - last_signal_time
        
        if time_diff < timedelta(hours=SIGNAL_COOLDOWN_HOURS):
            return False
    
    return True

def record_signal(symbol, timeframe):
    history = load_signal_history()
    key = f"{symbol}_{timeframe}"
    history[key] = datetime.now().isoformat()
    save_signal_history(history)

# --- TELEGRAM ---
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'HTML'
    }
    try:
        response = requests.post(url, json=payload, verify=False, timeout=30)
        return True
    except Exception as e:
        print(f"❌ Telegram ошибка: {e}")
        return False

# --- БИРЖА ---
def init_exchange():
    try:
        exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        print("✅ Биржа инициализирована")
        return exchange
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return None

# --- ПРОВЕРКА СИГНАЛА ---
def check_signal(exchange, symbol, timeframe, volume_24h):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=100)
        if len(bars) < 50:
            return False, ""
            
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['rsi'] = ta.rsi(df['close'], length=RSI_PERIOD)
        df['sma_of_rsi'] = ta.sma(df['rsi'], length=SMA_PERIOD)
        
        df = df.dropna().reset_index(drop=True)
        
        if len(df) < 2:
            return False, ""
        
        prev_rsi = df['rsi'].iloc[-2]
        curr_rsi = df['rsi'].iloc[-1]
        prev_sma = df['sma_of_rsi'].iloc[-2]
        curr_sma = df['sma_of_rsi'].iloc[-1]
        
        crossover = (prev_rsi <= prev_sma) and (curr_rsi > curr_sma)
        below_40 = (curr_rsi < 40) and (curr_sma < 40)
        
        if crossover and below_40:
            if not can_send_signal(symbol, timeframe):
                return False, ""
            
            record_signal(symbol, timeframe)
            
            current_price = df['close'].iloc[-1]
            coin_name = symbol.replace('/USDT', '')
            
            # 🎯 РАСЧЕТ УРОВНЕЙ (Стоп 3.5%, Тейк 1: 3%, Тейк 2: 7%)
            stop_loss_price = current_price * 0.965   # -3.5%
            tp1_price = current_price * 1.03          # +3% (частичная фиксация)
            tp2_price = current_price * 1.07          # +7% (полная фиксация)
            
            message = (
                f"🚨 <b>СИГНАЛ НА ПОКУПКУ!</b>\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💰 <b>Монета:</b> {coin_name}\n"
                f"💵 <b>Пара:</b> {symbol.replace('/', '')}\n"
                f"💲 <b>Цена входа:</b> ${current_price:.8f}\n"
                f"📊 <b>Объем 24ч:</b> ${volume_24h:,.0f}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"🎯 <b>ЦЕЛЬ 1 (+3%):</b> ${tp1_price:.8f} <i>(Забрать 50%)</i>\n"
                f"🎯 <b>ЦЕЛЬ 2 (+7%):</b> ${tp2_price:.8f} <i>(Забрать остаток)</i>\n"
                f"🛑 <b>СТОП-ЛОСС (-3.5%):</b> ${stop_loss_price:.8f}\n"
                f"━━━━━━━━━━━━━━━━\n"
                f"💡 <i>Совет: Забери половину на Цели 1 и переведи стоп в безубыток!</i>\n"
                f"⏱ <b>Таймфрейм:</b> {timeframe}\n"
                f"📈 <b>RSI:</b> {curr_rsi:.2f} | <b>SMA:</b> {curr_sma:.2f}\n"
                f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"🔄 #{coin_name}"
            )
            return True, message
        
        return False, ""
            
    except Exception as e:
        return False, ""

# --- ГЛАВНАЯ ---
def main():
    print("="*50)
    print("🚀 ЗАПУСК СКАНЕРА СИГНАЛОВ (С УРОВНЯМИ)")
    print("="*50)
    print(f"⏱ Таймфреймы: {TIMEFRAMES}")
    print(f"💰 Мин. объем: ${VOLUME_MIN:,}")
    print(f"⏰ Кулдаун: {SIGNAL_COOLDOWN_HOURS} часов")
    print("="*50)
    
    exchange = init_exchange()
    if exchange is None:
        return
    
    send_telegram_message(
        f"🤖 <b>Сканер запущен!</b>\n\n"
        f"⏱ Таймфреймы: {', '.join(TIMEFRAMES)}\n"
        f"💰 Мин. объем: ${VOLUME_MIN:,}\n"
        f"🎯 Стратегия: SL 3.5% | TP1 3% | TP2 7%\n"
        f"⏰ Кулдаун: {SIGNAL_COOLDOWN_HOURS} часов"
    )
    
    # Получаем все монеты с объёмом один раз
    print("\n📊 Загружаем список монет...")
    tickers = exchange.fetch_tickers()
    
    qualified_symbols = []
    for symbol, ticker in tickers.items():
        if symbol.endswith('/USDT'):
            volume_24h = float(ticker.get('quoteVolume', 0) or 0)
            if volume_24h >= VOLUME_MIN:
                qualified_symbols.append((symbol, volume_24h))
    
    print(f"✅ Найдено {len(qualified_symbols)} монет с объёмом > ${VOLUME_MIN:,}")
    
    # Бесконечный цикл проверки
    cycle = 1
    while True:
        try:
            print(f"\n{'='*50}")
            print(f"🔄 ЦИКЛ #{cycle} | {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*50}")
            
            signals_found = 0
            
            for timeframe in TIMEFRAMES:
                print(f"\n⏰ Таймфрейм: {timeframe}")
                
                for i, (symbol, volume) in enumerate(qualified_symbols, 1):
                    if i % 50 == 0:
                        print(f"📈 [{i}/{len(qualified_symbols)}] {symbol}")
                    
                    signal_found, message = check_signal(exchange, symbol, timeframe, volume)
                    if signal_found:
                        print(f"✅ СИГНАЛ! {symbol} {timeframe}")
                        send_telegram_message(message)
                        signals_found += 1
            
            print(f"\n🎯 Цикл #{cycle} завершён. Найдено сигналов: {signals_found}")
            
            # Обновляем список монет каждые 10 циклов
            if cycle % 10 == 0:
                print("\n🔄 Обновляем список монет...")
                tickers = exchange.fetch_tickers()
                qualified_symbols = []
                for symbol, ticker in tickers.items():
                    if symbol.endswith('/USDT'):
                        volume_24h = float(ticker.get('quoteVolume', 0) or 0)
                        if volume_24h >= VOLUME_MIN:
                            qualified_symbols.append((symbol, volume_24h))
                print(f"✅ Обновлено: {len(qualified_symbols)} монет")
            
            cycle += 1
            
            # Минимальная пауза между циклами (10 секунд)
            print("\n⏳ Пауза 10 секунд...")
            time.sleep(10)
            
        except KeyboardInterrupt:
            print("\n👋 Остановлено")
            send_telegram_message("👋 Сканер остановлен")
            break
            
        except Exception as e:
            print(f"❌ Ошибка: {e}")
            time.sleep(30)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Остановлено")

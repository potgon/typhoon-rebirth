Actúa como un Arquitecto de Software Senior experto en Trading Algorítmico y Python. Tu tarea es construir un "Hybrid Regime-Switching Trading Bot" completo, modular y listo para producción usando la librería `ccxt`.

### 1. Especificaciones de Arquitectura
* **Lenguaje:** Python 3.12
* **Contenedorización:** Docker (Crear Dockerfile y docker-compose.yml).
* **Persistencia:** SQLite (archivo `bot_data.db` en un volumen persistente).
* **Librerías Clave:** `ccxt` (interacción exchange), `pandas` (cálculos), `pandas_ta` (indicadores técnicos), `sqlalchemy` (ORM simple).
* **Estructura:** Monolito Modular. Un `main.py` orquesta las clases.

### 2. Estructura de Archivos Requerida
Project/
├── data/ (Volumen Docker)
├── src/
│   ├── config.py (Variables de entorno y settings)
│   ├── database.py (Manejo de SQLite)
│   ├── exchange_client.py (Wrapper de ccxt con manejo de errores y retries)
│   ├── analysis_tool.py (Script standalone para calcular métricas)
│   ├── strategies/
│   │   ├── base_strategy.py (Clase padre abstracta)
│   │   ├── mean_reversion.py (Lógica Bollinger+RSI)
│   │   └── trend_follower.py (Lógica Donchian+EMA)
│   └── watchman.py (Detector de régimen de mercado)
├── main.py (Bucle infinito y orquestador)
├── requirements.txt
├── Dockerfile
└── .env.example

### 3. Lógica Detallada de los Módulos

#### A. The Watchman (Detector de Régimen)
Debe analizar velas de **1 Hora (1h)**.
* Calcula ADX (14).
* **Output:**
    * Si ADX < 25 -> Retorna `MARKET_REGIME.RANGING`
    * Si ADX >= 25 -> Retorna `MARKET_REGIME.TRENDING`

#### B. Estrategia 1: Mean Reversion (Solo activa en RANGING)
Timeframe: **15m**.
* **Entrada Long:** Cierre de vela < Banda Bollinger Inferior (20, 2) AND RSI(14) < 30.
* **Entrada Short:** Cierre de vela > Banda Bollinger Superior (20, 2) AND RSI(14) > 70.
* **Salida:** Tocar la Media Móvil Simple (SMA 20) o Stop Loss (1.5x ATR).

#### C. Estrategia 2: Trend Sniper (Solo activa en TRENDING)
Timeframe: **1h**.
* **Filtro:** Precio por encima (Long) o debajo (Short) de EMA 200.
* **Entrada Long:** Precio > Donchian Channel High (20 periodos).
* **Entrada Short:** Precio < Donchian Channel Low (20 periodos).
* **Salida:** Trailing Stop dinámico usando la banda opuesta del Canal Donchian.

#### D. Base de Datos & Análisis
* Crea una tabla `trades` que registre: `id, symbol, strategy_used, side, entry_price, exit_price, size, pnl_absolute, pnl_percent, entry_time, exit_time`.
* El script `analysis_tool.py` debe poder ejecutarse manualmente y mostrar en consola:
    * Winrate Total y por Estrategia.
    * Profit Factor.
    * Max Drawdown.
    * Total PnL en USDT.

#### E. Orquestador (main.py)
* Bucle infinito (`while True`).
* Verifica régimen con Watchman.
* Si hay posición abierta de una estrategia "inactiva" (ej. reversión abierta y mercado cambia a tendencia), **NO cerrarla forzosamente**. Dejar que la estrategia gestione su salida (TP/SL) y luego bloquear nuevas entradas.
* Manejo robusto de errores de red (sleep y reintento).
* Uso de Binance Testnet via variables de entorno.

### 4. Entregable
Genera el código completo para todos los archivos mencionados, asegurando que las clases de estrategia hereden correctamente, el manejo de base de datos sea seguro (thread-safe si es necesario) y el Dockerfile esté optimizado.
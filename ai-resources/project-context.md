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

### 5. Anexo: Mejoras Técnicas Obligatorias (Estabilidad y Logging)
Para asegurar la robustez del sistema en producción, implementa las siguientes mejoras lógicas sobre la arquitectura base:

#### 5.1. Implementación de Histéresis en el Watchman (Anti-Whipsaw)
Para evitar cambios constantes de régimen cuando el ADX oscila alrededor del umbral (ej. 24.9 -> 25.1 -> 24.8), la lógica de transición debe tener memoria de estado (Histéresis):

Definir dos umbrales: ADX_TREND_START = 25 y ADX_RANGE_RETURN = 20.

Lógica de Cambio:

Si el estado actual es RANGING: Solo cambiar a TRENDING si ADX > 25.

Si el estado actual es TRENDING: Solo volver a RANGING si ADX < 20.

Resultado: Se crea una zona "colchón" entre 20 y 25 donde el bot mantiene su decisión anterior, evitando el ruido.

#### 5.2. Mecanismo de Cooldown post-cambio
Al producirse un cambio de régimen (de Rango a Tendencia o viceversa), el Orquestador debe activar un COOLDOWN_TIMER de 15 minutos (o 1 vela del timeframe base).

Durante este tiempo, no se permiten nuevas entradas.

Objetivo: Permitir que la volatilidad del cambio se asiente y confirmar que el cambio de régimen es real antes de arriesgar capital.

#### 5.3. Sistema de Logging Estructurado (Auditoría Forense)
Sustituir los print básicos por el módulo logging de Python configurado para escribir tanto en consola como en un archivo rotativo bot_activity.log. El formato del log debe ser parseable y contener métricas clave en cada decisión crítica.

Formato requerido: %(asctime)s - [REGIME: %(regime)s] - [STRATEGY: %(strategy)s] - %(levelname)s - %(message)s

Ejemplo de Log Crítico (Entry): "SIGNAL GENERATED | Symbol: BTC/USDT | Side: LONG | Price: 95000 | Ind: RSI=28, BB_Low=95100 | Reason: Oversold Condition"

Ejemplo de Log Crítico (Regime Switch): "REGIME CHANGE DETECTED | Old: RANGING | New: TRENDING | ADX Value: 26.5 | Action: Pausing Mean Reversion Strategy"
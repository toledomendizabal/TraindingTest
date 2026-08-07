# Diagnóstico: "La forma online no ejecuta operaciones en MetaTrader 5"

## Resumen (léelo primero)

Revisé `app/services/mt5_executor.py`, `app/core/config.py` y `requirements.txt`.
El código de ejecución en sí está bien escrito y ya incluye manejo de errores
defensivo. La causa **más probable, con mucha diferencia**, de que la versión
"online" no genere operaciones en MT5 es **arquitectónica, no un bug de
código**:

> El paquete oficial de Python `MetaTrader5` se conecta a una terminal MT5
> **instalada y abierta en la MISMA máquina**, por IPC local -- **no es una
> API remota**. Si tu backend "online" corre en un servidor Linux (Docker,
> un VPS Linux, Railway, Render, etc.), el paquete `MetaTrader5`:
> - **ni siquiera se puede importar** (es un binario específico de Windows),
> - por eso `mt5_executor.py` ya detecta esto en tiempo de import
>   (`MT5_AVAILABLE = False`) y **todas las llamadas devuelven `None`/`False`
>   de forma silenciosa**, sin lanzar ninguna excepción, para no tumbar el
>   resto del sistema.

Resultado: las señales se generan, se guardan en Excel, se notifican por
Telegram... pero **nunca llegan a MT5**, y no aparece ningún error visible
porque el propio diseño del módulo está pensado para "fallar en silencio"
cuando MT5 no está disponible (una decisión de diseño razonable para no
romper el resto del sistema en un entorno sin MT5 -- pero que hace que el
problema pase desapercibido si no se revisan los logs con atención).

## Cómo confirmarlo en 2 minutos

Ejecuta esto en el servidor donde corre la versión "online":

```bash
python3 -c "import MetaTrader5; print('MT5 SÍ se pudo importar')"
```

- Si ves `ModuneNotFoundError` / `ImportError` -> **confirmado**, ese es el
  problema. Sigue a la sección "Soluciones" abajo.
- Si se importa sin error -> pasa al checklist de la sección siguiente
  (el problema es de configuración/credenciales, no de plataforma).

También puedes revisar los logs del backend buscando estas líneas exactas
(ya existen en el código, en `app/services/mt5_executor.py`):

```
grep -i "MetaTrader5.*no disponible\|MT5.*no disponible\|MT5_AVAILABLE" logs/*.log
```

## Checklist completo (en orden de probabilidad)

1. **Plataforma** (la causa más común): `MetaTrader5` no se puede importar
   porque el backend corre en Linux/Mac. -> Ver "Soluciones".
2. **Interruptor de seguridad apagado**: `MT5_LIVE_TRADING_ENABLED=false` en
   `.env` es el valor por defecto **a propósito** (para no operar en vivo
   por accidente). Verifica en el servidor:
   ```bash
   grep MT5_LIVE_TRADING_ENABLED .env
   ```
   Debe decir `true` para que se envíen órdenes reales.
3. **Credenciales**: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` en `.env`
   deben ser exactamente los mismos que usas para iniciar sesión manualmente
   en la terminal MT5 (número de cuenta, contraseña **de trading** -- no la
   de "solo lectura" -- y el nombre EXACTO del servidor del bróker, ej.
   `ICMarketsSC-Demo`, no solo "ICMarkets").
4. **Terminal MT5 no está abierta/logueada**: `mt5.initialize()` requiere
   que la terminal ya esté abierta en el escritorio de esa máquina (o al
   menos instalada, si le pasas la ruta al ejecutable). Si el servidor
   Windows se reinició y la terminal no está configurada para autoiniciar y
   auto-loguearse, `initialize()` fallará silenciosamente en cada intento.
5. **Símbolo no coincide con el bróker**: algunos brokers usan sufijos
   (`EURUSD.pro`, `EURUSDm`, `XAUUSD.s`). El código ya intenta resolverlo
   automáticamente (`_resolve_symbol` en `mt5_executor.py`), pero si tu
   bróker usa un formato inusual puede seguir fallando para símbolos
   nuevos como los cruces JPY o `WTI`/`BRENT`/`COPPER` que se agregaron
   ahora -- confírmalos manualmente en el "Market Watch" de la terminal.
6. **Firewall/antivirus** bloqueando el proceso `terminal64.exe` o su
   comunicación IPC con Python (menos común, pero ocurre en VPS con
   políticas de seguridad estrictas).

## Soluciones si el problema es de plataforma (punto 1)

No existe un "arreglo de código" para que el paquete `MetaTrader5` de Python
funcione de forma remota -- es una limitación del paquete mismo. Las
opciones reales son:

- **Opción A (recomendada): mover el backend a un VPS Windows.**
  Instala Python + este proyecto + la terminal MT5 en un mismo servidor
  Windows (VPS), inicia sesión en MT5 ahí y déjalo corriendo. Es el enfoque
  estándar para bots de trading con MT5 y el que da menos sorpresas.
- **Opción B: Wine en el servidor Linux actual.**
  Es posible ejecutar MT5 bajo Wine junto con una build de Python para
  Windows, pero es notoriamente frágil (actualizaciones de MT5 rompen la
  configuración de Wine con cierta frecuencia) y no se recomienda para un
  sistema que opera con dinero real sin monitoreo constante.
- **Opción C: bridge por archivos, como ya hace `mt4_monitor.py`.**
  Noté que el proyecto ya tiene un enfoque de monitoreo basado en archivos
  para MT4 (`app/services/mt4_monitor.py`). Si tu bróker/terminal soporta
  Expert Advisors, se puede construir un puente similar para MT5: el
  backend Linux escribe "órdenes pendientes" a un archivo/cola (o a una
  base de datos), y un Expert Advisor corriendo en la terminal MT5 (en
  Windows) las lee y las ejecuta, escribiendo el resultado de vuelta. Esto
  es más trabajo de desarrollo (un EA en MQL5 + protocolo de intercambio de
  archivos) pero si ya tienes una VM Windows con MT5 abierto para MT4, es
  la opción que menos cambia tu arquitectura "online" actual.

## Qué NO cambié

No toqué `mt5_executor.py` -- el código en sí ya está bien defendido
(timeouts, reintentos, manejo de excepciones, resolución de símbolo). Si
después de revisar este checklist el problema persiste con MT5_AVAILABLE=True
y LIVE_TRADING_ENABLED=true, dime el mensaje de error EXACTO que aparece en
los logs (`logs/*.log`, busca líneas con "MT5" o "mt5.last_error") y ahí sí
reviso el código puntual con datos reales en vez de adivinar.

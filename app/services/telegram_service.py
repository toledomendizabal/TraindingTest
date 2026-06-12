"""Telegram notification service."""
import httpx
from datetime import datetime
from typing import Optional
from loguru import logger
from app.core.config import settings


class TelegramService:
    """Service for sending Telegram notifications."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.base_url = self.BASE_URL.format(token=self.token)
        self._client: Optional[httpx.AsyncClient] = None

    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self):
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Send a message to Telegram."""
        try:
            client = await self.get_client()
            response = await client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": parse_mode
                }
            )

            if response.status_code == 200:
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.warning(f"Telegram send failed: {response.text}")
                return False

        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return False

    async def send_signal_notification(self, signal) -> bool:
        """Send a trading signal notification."""
        emoji = "🟢" if signal.direction.value == "BUY" else "🔴"

        message = (
            f"{emoji} <b>NUEVA SEÑAL - {signal.asset}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Dirección: <b>{signal.direction.value}</b>\n"
            f"💰 Entrada: <code>{signal.entry_price}</code>\n"
            f"🛑 Stop Loss: <code>{signal.stop_loss}</code> ({signal.sl_pips} pips)\n"
            f"🎯 TP1 (1:3): <code>{signal.take_profit_1}</code> ({signal.tp1_pips} pips)\n"
            f"🎯 TP2 (1:6): <code>{signal.take_profit_2}</code> ({signal.tp2_pips} pips)\n"
            f"🎯 TP3 (1:10): <code>{signal.take_profit_3}</code> ({signal.tp3_pips} pips)\n"
            f"📐 Lotaje: <code>{signal.lot_size}</code>\n"
            f"⏱ Timeframe: {signal.timeframe}\n"
            f"🏦 Sesión: {signal.session}\n"
            f"📈 Indicadores: {signal.indicators_met}/18\n"
            f"⭐ Score: {signal.score}%\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {signal.created_at.strftime('%Y-%m-%d %H:%M:%S') if signal.created_at else ''}"
        )

        return await self.send_message(message)

    async def send_close_notification(self, signal_id: str, status: str,
                                       close_price: float, profit_loss: float, asset: str = "Unknown") -> bool:
        """Send position close notification."""
        emoji = "✅" if profit_loss > 0 else "❌"
        result = "GANANCIA" if profit_loss > 0 else "PÉRDIDA"

        message = (
            f"{emoji} <b>POSICIÓN CERRADA - {asset}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: {signal_id}\n"
            f"📊 Estado: {status}\n"
            f"💰 Precio Cierre: <code>{close_price}</code>\n"
            f"{'💵' if profit_loss > 0 else '💸'} {result}: <code>${profit_loss:.2f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        return await self.send_message(message)

    async def send_test_message(self) -> bool:
        """Send daily test message at 9:00 AM."""
        message = (
            f"🤖 <b>TradingSignal Pro - Mensaje de Prueba</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Sistema operativo\n"
            f"📅 Fecha: {datetime.now().strftime('%Y-%m-%d')}\n"
            f"🕐 Hora: {datetime.now().strftime('%H:%M:%S')}\n"
            f"🏦 Sesión actual: {self._get_session()}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Monitoreando {len(settings.ACTIVE_ASSETS)} activos"
        )

        return await self.send_message(message)

    async def send_backtesting_report(self, report: dict) -> bool:
        """Send backtesting report notification."""
        message = (
            f"📊 <b>REPORTE DE BACKTESTING</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Fecha: {report.get('date', '')}\n"
            f"📈 Total Señales: {report.get('total_signals', 0)}\n"
            f"✅ Ganadoras: {report.get('winning_signals', 0)}\n"
            f"❌ Perdedoras: {report.get('losing_signals', 0)}\n"
            f"🎯 Win Rate: {report.get('win_rate', 0):.1f}%\n"
            f"💰 Profit Factor: {report.get('profit_factor', 0):.2f}\n"
            f"📉 Max Drawdown: {report.get('max_drawdown', 0):.2f}%\n"
            f"💵 Ganancia Neta: ${report.get('net_profit', 0):.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📧 Reporte enviado por correo"
        )

        return await self.send_message(message)

    def _get_session(self) -> str:
        """Get current trading session."""
        hour = datetime.utcnow().hour
        if 0 <= hour < 8:
            return "Tokyo 🇯🇵"
        elif 8 <= hour < 13:
            return "London 🇬🇧"
        elif 13 <= hour < 22:
            return "New York 🇺🇸"
        else:
            return "Tokyo 🇯🇵"


# Singleton instance
telegram_service = TelegramService()

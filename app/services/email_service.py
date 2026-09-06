"""Email service using Gmail API with OAuth2."""
import os
import asyncio
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Optional
from loguru import logger
from app.core.config import settings

# CAMBIO CRÍTICO (fix, 2026-09-04 -- "el sistema se detiene por el correo
# electrónico"): confirmado con logs reales de 2 días distintos
# (2026-09-02 y 2026-09-03): ambos logs terminan EXACTAMENTE en la línea
# "Starting Gmail OAuth flow..." -- el programa completo se queda
# congelado ahí, sin ningún error posterior, hasta que alguien lo
# reinicia manualmente.
#
# Causa: `flow.run_local_server(port=0)` es una llamada SÍNCRONA y
# BLOQUEANTE que levanta un servidor HTTP local y espera indefinidamente
# a que una persona complete el login de Google en un navegador. Se
# llamaba directamente dentro de un método `async def`, sin ningún
# timeout y sin correrla en un hilo aparte -- eso bloquea TODO el event
# loop de asyncio (el proceso completo, incluyendo el motor de señales,
# el monitor de posiciones, MT5, todo) mientras espera un login
# interactivo que nunca va a llegar en un servidor sin navegador.
#
# Esto se dispara cada vez que el refresh token de Gmail expira o se
# revoca (visto en los logs: "invalid_grant: Token has been expired or
# revoked") -- en ese caso el código intentaba relanzar el flujo
# interactivo completo, congelando el sistema el resto del día (y del
# siguiente, y del que sigue...).
#
# Corrección: TODA llamada de red/interactiva de este archivo ahora corre
# en un hilo aparte (`asyncio.to_thread`) envuelta en
# `asyncio.wait_for(..., timeout=EMAIL_TIMEOUT_SECONDS)` (60s por
# defecto, configurable). Si no responde a tiempo, se cancela, se
# registra un WARNING claro, y el programa SIGUE corriendo con el correo
# deshabilitado para ese intento -- exactamente como se pidió.
EMAIL_TIMEOUT_SECONDS = getattr(settings, "EMAIL_TIMEOUT_SECONDS", 60)


class EmailService:
    """Service for sending emails via Gmail API."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

    def __init__(self):
        self.credentials = None
        self.service = None
        self._initialized = False

    async def initialize(self):
        """
        Initialize Gmail service with OAuth2 credentials.

        CAMBIO CRÍTICO (fix, 2026-09-04): tanto el refresco del token
        como el flujo interactivo de login ahora corren con un timeout de
        `EMAIL_TIMEOUT_SECONDS` (60s por defecto) -- si no responden a
        tiempo, se continúa sin correo en vez de congelar el sistema. Ver
        el comentario al inicio del archivo para el detalle completo del
        bug encontrado.
        """
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build

            token_path = os.path.join(settings.CONFIG_DIR, "token.json")
            client_secret_path = os.path.join(settings.CONFIG_DIR, "client_secret.json")

            if os.path.exists(token_path):
                self.credentials = Credentials.from_authorized_user_file(token_path, self.SCOPES)

            # Use credentials if valid, or try to refresh them
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                try:
                    # CAMBIO: el refresco de token es una llamada de red
                    # síncrona (bloqueante) -- se corre en un hilo aparte
                    # con timeout, igual que el flujo interactivo de abajo,
                    # para que un hipo de red no congele el proceso.
                    await asyncio.wait_for(
                        asyncio.to_thread(self.credentials.refresh, Request()),
                        timeout=EMAIL_TIMEOUT_SECONDS,
                    )
                    with open(token_path, "w") as token:
                        token.write(self.credentials.to_json())
                    logger.info("Gmail token refreshed successfully")
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Gmail: el refresco del token no respondió en {EMAIL_TIMEOUT_SECONDS}s -- "
                        f"se continúa SIN correo por ahora. El sistema sigue funcionando con "
                        f"normalidad (esto no bloquea señales, MT5 ni el resto del proceso)."
                    )
                    self.credentials = None
                except Exception as e:
                    logger.error(f"Failed to refresh Gmail token: {e}")
                    self.credentials = None

            # Only run local server if no valid credentials exist
            if not self.credentials or not self.credentials.valid:
                if os.path.exists(client_secret_path):
                    logger.info(f"Starting Gmail OAuth flow (timeout {EMAIL_TIMEOUT_SECONDS}s)...")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        client_secret_path, self.SCOPES
                    )
                    try:
                        # CAMBIO CRÍTICO: antes esta línea bloqueaba TODO el
                        # proceso indefinidamente esperando un login manual
                        # en un navegador -- que nunca llega en un servidor
                        # headless. Ahora corre en un hilo aparte con
                        # timeout: si nadie completa el login en
                        # `EMAIL_TIMEOUT_SECONDS`, se cancela y el programa
                        # sigue funcionando sin correo.
                        self.credentials = await asyncio.wait_for(
                            asyncio.to_thread(flow.run_local_server, port=0),
                            timeout=EMAIL_TIMEOUT_SECONDS,
                        )
                        # Save token
                        if self.credentials:
                            with open(token_path, "w") as token:
                                token.write(self.credentials.to_json())
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"Gmail: nadie completó el login interactivo en "
                            f"{EMAIL_TIMEOUT_SECONDS}s -- se continúa SIN correo. El resto "
                            f"del sistema (señales, MT5, monitoreo) sigue funcionando con "
                            f"normalidad. Para reactivar el correo, el login de Gmail debe "
                            f"completarse manualmente (esto requiere un navegador -- no es "
                            f"viable en un servidor sin interfaz gráfica; ver "
                            f"docs/DIAGNOSTICO_EMAIL.md)."
                        )
                        self.credentials = None
                else:
                    logger.warning("client_secret.json not found. Gmail authentication skipped.")

            if self.credentials:
                self.service = build("gmail", "v1", credentials=self.credentials)
                self._initialized = True
                logger.info("Gmail service initialized successfully")
            else:
                self._initialized = False

        except Exception as e:
            logger.error(f"Error initializing Gmail service: {e}")
            self._initialized = False

    async def send_backtest_report(self, result, report_type: str) -> bool:
        """Send backtesting report via email."""
        try:
            if not self._initialized:
                await self.initialize()

            if not self.service:
                logger.warning("Gmail service not available, skipping email")
                return False

            subject = f"TradingSignal Pro - Reporte Backtesting {'Diario' if report_type == 'daily' else 'Semanal'} - {result.date}"

            body = self._format_email_body(result, report_type)

            message = MIMEMultipart()
            message["to"] = settings.EMAIL_RECIPIENT
            message["from"] = settings.EMAIL_SENDER
            message["subject"] = subject

            message.attach(MIMEText(body, "html"))

            # Attach report file if exists
            from app.services.backtesting import backtesting_service
            report_content = backtesting_service.get_latest_report(report_type)
            if report_content:
                date_str = datetime.now().strftime("%Y%m%d")
                filename = f"[{date_str}]AnalisisBackTesting_{report_type}.txt"

                attachment = MIMEBase("application", "octet-stream")
                attachment.set_payload(report_content.encode("utf-8"))
                encoders.encode_base64(attachment)
                attachment.add_header(
                    "Content-Disposition", f"attachment; filename={filename}"
                )
                message.attach(attachment)

            # Send
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            # CAMBIO (fix, 2026-09-04): el envío real también es una
            # llamada de red bloqueante -- mismo timeout que el resto del
            # archivo, por consistencia y para no reabrir el mismo tipo de
            # bloqueo en otro punto.
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(
                        lambda: self.service.users().messages().send(
                            userId="me", body={"raw": raw}
                        ).execute()
                    ),
                    timeout=EMAIL_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Gmail: el envío del correo no respondió en {EMAIL_TIMEOUT_SECONDS}s -- "
                    f"se omite este reporte por correo, el sistema continúa con normalidad."
                )
                return False

            logger.info(f"Backtest email sent to {settings.EMAIL_RECIPIENT}")
            return True

        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return False

    def _format_email_body(self, result, report_type: str) -> str:
        """Format email body as HTML."""
        header = "Diario" if report_type == "daily" else "Semanal"

        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #1a1a2e; color: white; padding: 20px; text-align: center;">
                <h1 style="color: #00d4aa;">TradingSignal Pro</h1>
                <h2>Reporte de Backtesting {header}</h2>
                <p>Fecha: {result.date}</p>
            </div>

            <div style="padding: 20px;">
                <h3 style="color: #333;">Métricas de Rendimiento</h3>
                <table style="width: 100%; border-collapse: collapse;">
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 10px; border: 1px solid #ddd;">Total Señales</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{result.total_signals}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;">Win Rate</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: {'green' if result.win_rate >= 55 else 'red'};">{result.win_rate}%</td>
                    </tr>
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 10px; border: 1px solid #ddd;">Profit Factor</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{result.profit_factor}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border: 1px solid #ddd;">Max Drawdown</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right;">{result.max_drawdown}%</td>
                    </tr>
                    <tr style="background: #f5f5f5;">
                        <td style="padding: 10px; border: 1px solid #ddd;">Ganancia Neta</td>
                        <td style="padding: 10px; border: 1px solid #ddd; text-align: right; color: {'green' if result.net_profit >= 0 else 'red'};">${result.net_profit}</td>
                    </tr>
                </table>

                <h3 style="color: #333; margin-top: 20px;">Recomendaciones</h3>
                <ul>
                    {"".join(f'<li>{rec}</li>' for rec in result.recommendations)}
                </ul>

                <h3 style="color: #333;">Ajustes de Indicadores</h3>
                <ul>
                    {"".join(f'<li>{adj}</li>' for adj in result.indicator_adjustments)}
                </ul>
            </div>

            <div style="background: #333; color: white; padding: 10px; text-align: center; font-size: 12px;">
                <p>TradingSignal Pro - Sistema Automatizado de Trading</p>
            </div>
        </body>
        </html>
        """
        return html

    def is_authenticated(self) -> bool:
        """Check if Gmail service is authenticated."""
        return self._initialized and self.service is not None


# Singleton instance
email_service = EmailService()

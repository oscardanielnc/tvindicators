"""Notificaciones (alertas) por ntfy y/o Telegram. Sin dependencias extra (urllib).
Configurar por entorno:
  TVBOT_NTFY_URL = https://ntfy.sh/<tu-topico>
  TVBOT_TG_TOKEN = <bot token> · TVBOT_TG_CHAT = <chat id>
Si no hay nada configurado, notify() es no-op (devuelve False)."""
import os
import urllib.parse
import urllib.request


def notify(msg, title="tvbot"):
    sent = False
    ntfy = os.getenv("TVBOT_NTFY_URL")
    if ntfy:
        try:
            req = urllib.request.Request(ntfy, data=msg.encode("utf-8"),
                                         headers={"Title": title, "Priority": "high"})
            urllib.request.urlopen(req, timeout=10); sent = True
        except Exception:
            pass
    tok, chat = os.getenv("TVBOT_TG_TOKEN"), os.getenv("TVBOT_TG_CHAT")
    if tok and chat:
        try:
            url = f"https://api.telegram.org/bot{tok}/sendMessage"
            data = urllib.parse.urlencode({"chat_id": chat, "text": f"[{title}] {msg}"}).encode()
            urllib.request.urlopen(url, data=data, timeout=10); sent = True
        except Exception:
            pass
    return sent

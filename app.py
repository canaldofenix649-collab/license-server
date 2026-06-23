"""
==============================================================
  SERVIDOR DE LICENÇAS — Pexels Pro Bulk Downloader
==============================================================
  Responsabilidades:
  1. Receber webhook do Ckato quando um pagamento é aprovado
  2. Gerar um código de ativação único (ex: PXPRO-XXXX-XXXX-XXXX)
  3. Salvar o código no banco SQLite com email e validade
  4. Enviar email automático para o cliente com o código
  5. Expor endpoint /activate para o app desktop validar códigos

  Deploy: Railway (https://railway.app) — gratuito para começar
==============================================================
"""

import os
import re
import hmac
import uuid
import json
import sqlite3
import hashlib
import secrets
import string
import requests as http_requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

# ==============================================================
# CONFIGURAÇÃO (via variáveis de ambiente no Railway)
# ==============================================================
# Chave secreta para validar webhooks do Ckato (copie do painel do Ckato)
CKATO_WEBHOOK_SECRET = os.environ.get("CKATO_WEBHOOK_SECRET", "")

# Chave API do Brevo (https://app.brevo.com) — para envio de emails via HTTP
BREVO_API_KEY     = os.environ.get("BREVO_API_KEY", "")
EMAIL_FROM_NAME   = os.environ.get("EMAIL_FROM_NAME", "Pexels Pro Downloader")
EMAIL_FROM_ADDR   = os.environ.get("EMAIL_FROM_ADDR", "canaldofenix649@gmail.com")

# Chave interna para proteger o endpoint /activate contra uso não autorizado
ACTIVATION_API_KEY = os.environ.get("ACTIVATION_API_KEY", "mude-esta-chave-secreta")

# Número de dias padrão de validade da licença
LICENSE_DAYS = int(os.environ.get("LICENSE_DAYS", "30"))

# Caminho do banco de dados SQLite
DB_PATH = os.environ.get("DB_PATH", "licenses.db")

# ==============================================================
# BANCO DE DADOS
# ==============================================================

def get_db():
    """Retorna uma conexão com o banco SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Cria as tabelas necessárias se não existirem."""
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                code        TEXT    UNIQUE NOT NULL,
                email       TEXT    NOT NULL,
                ckato_order TEXT,
                status      TEXT    NOT NULL DEFAULT 'active',
                created_at  TEXT    NOT NULL,
                expires_at  TEXT    NOT NULL,
                activated_at TEXT,
                device_id   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS webhook_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                received_at TEXT NOT NULL,
                payload     TEXT NOT NULL,
                status      TEXT NOT NULL
            )
        """)
        conn.commit()

# ==============================================================
# GERAÇÃO DE CÓDIGO DE LICENÇA
# ==============================================================

def generate_license_code():
    """
    Gera um código de licença único no formato: PXPRO-XXXX-XXXX-XXXX
    Usa apenas letras maiúsculas e números sem caracteres ambíguos (0, O, I, 1, L).
    """
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    segments = []
    for _ in range(3):
        segment = "".join(secrets.choice(alphabet) for _ in range(4))
        segments.append(segment)
    return "PXPRO-" + "-".join(segments)

def create_license(email, ckato_order=None, days=None):
    """
    Gera e salva uma nova licença no banco.
    Retorna o código gerado.
    """
    if days is None:
        days = LICENSE_DAYS

    code = generate_license_code()
    now = datetime.utcnow()
    expires_at = now + timedelta(days=days)

    with get_db() as conn:
        conn.execute(
            """INSERT INTO licenses (code, email, ckato_order, status, created_at, expires_at)
               VALUES (?, ?, ?, 'active', ?, ?)""",
            (code, email.lower().strip(), ckato_order,
             now.isoformat(), expires_at.isoformat())
        )
        conn.commit()

    return code

# ==============================================================
# ENVIO DE EMAIL
# ==============================================================

def send_activation_email(to_email, license_code, expires_at_str):
    """Envia o código de ativação via Brevo HTTP API."""
    if not BREVO_API_KEY:
        print(f"[EMAIL] BREVO_API_KEY não configurado. Código gerado: {license_code} para {to_email}")
        return False

    try:
        expires_dt = datetime.fromisoformat(expires_at_str)
        expires_formatted = expires_dt.strftime("%d/%m/%Y")
    except Exception:
        expires_formatted = "30 dias"

    subject = "✅ Seu código de ativação — Pexels Pro Downloader"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #0a0f1e; color: #e2e8f0; margin: 0; padding: 0; }}
        .container {{ max-width: 560px; margin: 40px auto; background: #0e1726; border-radius: 16px; overflow: hidden; }}
        .header {{ background: linear-gradient(135deg, #1e40af, #0ea5e9); padding: 36px 40px; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 24px; color: #fff; }}
        .header p {{ margin: 8px 0 0; color: #bfdbfe; font-size: 14px; }}
        .body {{ padding: 36px 40px; }}
        .code-box {{ background: #050811; border: 2px solid #38bdf8; border-radius: 12px;
                     text-align: center; padding: 24px; margin: 24px 0; }}
        .code {{ font-family: 'Courier New', monospace; font-size: 28px; font-weight: bold;
                 color: #38bdf8; letter-spacing: 4px; }}
        .info {{ color: #94a3b8; font-size: 13px; margin-top: 12px; }}
        .steps {{ background: #0a1628; border-radius: 10px; padding: 20px 24px; margin: 24px 0; }}
        .steps h3 {{ color: #38bdf8; margin: 0 0 12px; font-size: 15px; }}
        .steps ol {{ margin: 0; padding-left: 20px; color: #94a3b8; font-size: 13px; line-height: 2; }}
        .footer {{ text-align: center; padding: 20px; color: #475569; font-size: 12px; }}
      </style>
    </head>
    <body>
      <div class="container">
        <div class="header">
          <h1>💠 Pexels Pro Downloader</h1>
          <p>Seu acesso premium foi confirmado!</p>
        </div>
        <div class="body">
          <p>Olá! Recebemos seu pagamento e seu acesso foi liberado. 🎉</p>
          <p>Use o código abaixo para ativar o aplicativo:</p>

          <div class="code-box">
            <div class="code">{license_code}</div>
            <div class="info">Válido até {expires_formatted}</div>
          </div>

          <div class="steps">
            <h3>📋 Como ativar:</h3>
            <ol>
              <li>Abra o <strong>Pexels Pro Downloader</strong></li>
              <li>Clique em <strong>"Já tenho um código"</strong></li>
              <li>Insira seu e-mail e o código acima</li>
              <li>Clique em <strong>Ativar</strong> — pronto!</li>
            </ol>
          </div>

          <p style="color: #64748b; font-size: 12px;">
            ⚠️ Este código é pessoal e intransferível. Guarde-o em local seguro.<br>
            Precisa de ajuda? Responda este email.
          </p>
        </div>
        <div class="footer">
          © Pexels Pro Downloader — Todos os direitos reservados
        </div>
      </div>
    </body>
    </html>
    """

    payload = {
        "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM_ADDR},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_body
    }

    try:
        resp = http_requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            },
            timeout=15
        )
        if resp.status_code in (200, 201):
            print(f"[EMAIL] Enviado com sucesso via Brevo para {to_email} (código: {license_code})")
            return True
        else:
            print(f"[EMAIL] Brevo retornou erro {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        print(f"[EMAIL] Erro ao enviar via Brevo para {to_email}: {e}")
        return False

# ==============================================================
# WEBHOOK DO CKATO
# ==============================================================

def verify_ckato_signature(payload_bytes, signature_header):
    """
    Valida a assinatura HMAC-SHA256 enviada pelo Ckato no header X-Ckato-Signature.
    Retorna True se válida, False caso contrário.
    """
    if not CKATO_WEBHOOK_SECRET:
        # Se não configurou o secret, aceita tudo (útil para testes iniciais)
        print("[WEBHOOK] AVISO: CKATO_WEBHOOK_SECRET não configurado. Aceitando sem validação.")
        return True

    expected = "sha256=" + hmac.new(
        CKATO_WEBHOOK_SECRET.encode(),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected, signature_header or "")

@app.route("/webhook/ckato", methods=["POST"])
def webhook_ckato():
    """
    Endpoint que o Ckato chama quando um pagamento é aprovado.
    Configure esta URL no painel do Ckato em: Produto > Configurações > Webhook
    URL completa: https://SEU-APP.railway.app/webhook/ckato
    """
    payload_bytes = request.get_data()
    signature     = request.headers.get("X-Ckato-Signature", "")

    # Valida assinatura
    if not verify_ckato_signature(payload_bytes, signature):
        print("[WEBHOOK] Assinatura inválida — rejeitando.")
        return jsonify({"error": "Invalid signature"}), 401

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400

    # Loga o webhook recebido
    with get_db() as conn:
        conn.execute(
            "INSERT INTO webhook_log (received_at, payload, status) VALUES (?, ?, ?)",
            (datetime.utcnow().isoformat(), json.dumps(data), "received")
        )
        conn.commit()

    print(f"[WEBHOOK] Payload recebido: {json.dumps(data, indent=2)}")

    # -------------------------------------------------------
    # Extrai dados do payload do Ckato
    # -------------------------------------------------------
    event_type  = data.get("event") or data.get("type") or data.get("status", "")
    order_id    = (data.get("order") or {}).get("id") or data.get("order_id") or data.get("id", "")

    def find_email_recursive(obj, depth=0):
        """Busca qualquer email válido em qualquer lugar do JSON."""
        if depth > 6:
            return ""
        if isinstance(obj, dict):
            # Tenta campos comuns primeiro
            for key in ("email", "customer_email", "buyer_email", "payer_email", "e_mail"):
                val = obj.get(key, "")
                if isinstance(val, str) and "@" in val and "." in val:
                    return val.strip().lower()
            # Tenta sub-objetos comuns do Cakto
            for key in ("customer", "buyer", "subscriber", "payer", "client",
                        "sale", "purchase", "transaction", "data", "order", "lead"):
                if key in obj:
                    found = find_email_recursive(obj[key], depth + 1)
                    if found:
                        return found
            # Varredura completa em todos os campos
            for val in obj.values():
                found = find_email_recursive(val, depth + 1)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = find_email_recursive(item, depth + 1)
                if found:
                    return found
        return ""

    customer_email = find_email_recursive(data)

    # Só processa eventos de pagamento aprovado
    approved_events = {"payment.approved", "order.approved", "approved", "paid", "complete", "completed", "purchase_approved", "purchase.approved"}
    is_approved = str(event_type).lower() in approved_events

    # Alguns webhooks do Ckato têm status aninhado em "payment"
    payment_status = (data.get("payment") or {}).get("status", "")
    if payment_status.lower() in {"approved", "paid"}:
        is_approved = True

    if not is_approved:
        print(f"[WEBHOOK] Evento ignorado: '{event_type}' — aguardando aprovação.")
        return jsonify({"ok": True, "message": "Event ignored (not approved)"}), 200

    if not customer_email or "@" not in customer_email:
        print(f"[WEBHOOK] Email inválido ou ausente: '{customer_email}'")
        return jsonify({"error": "Invalid or missing customer email"}), 422

    # Gera a licença
    code = create_license(email=customer_email, ckato_order=str(order_id))

    # Busca a validade para o email
    with get_db() as conn:
        row = conn.execute("SELECT expires_at FROM licenses WHERE code = ?", (code,)).fetchone()
        expires_at = row["expires_at"] if row else datetime.utcnow().isoformat()

    # Envia email
    send_activation_email(customer_email, code, expires_at)

    print(f"[WEBHOOK] Licença criada: {code} para {customer_email} (pedido: {order_id})")
    return jsonify({"ok": True, "license_code": code}), 200

# ==============================================================
# ENDPOINT DE ATIVAÇÃO (chamado pelo app desktop)
# ==============================================================

@app.route("/activate", methods=["POST"])
def activate_license():
    """
    O app desktop chama este endpoint para validar um código de ativação.
    Body JSON: { "code": "PXPRO-XXXX-XXXX-XXXX", "email": "...", "device_id": "..." }
    Header: X-API-Key: <ACTIVATION_API_KEY>
    """
    # Valida a API Key
    api_key = request.headers.get("X-API-Key", "")
    if api_key != ACTIVATION_API_KEY:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    body = request.get_json(force=True) or {}
    code      = str(body.get("code", "")).strip().upper()
    email     = str(body.get("email", "")).strip().lower()
    device_id = str(body.get("device_id", "")).strip()

    if not code or not email:
        return jsonify({"ok": False, "error": "Código e email são obrigatórios."}), 400

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM licenses WHERE code = ? AND LOWER(email) = ?",
            (code, email)
        ).fetchone()

        if not row:
            return jsonify({"ok": False, "error": "Código ou e-mail inválido."}), 404

        if row["status"] != "active":
            return jsonify({"ok": False, "error": f"Licença está com status: {row['status']}."}), 403

        # Verifica expiração
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.utcnow() > expires_at:
            conn.execute("UPDATE licenses SET status = 'expired' WHERE code = ?", (code,))
            conn.commit()
            return jsonify({"ok": False, "error": f"Licença expirada em {expires_at.strftime('%d/%m/%Y')}."}), 403

        # Verifica se o device_id mudou (evita compartilhamento)
        if row["device_id"] and row["device_id"] != device_id:
            return jsonify({"ok": False, "error": "Este código já foi ativado em outro computador."}), 403

        # Atualiza o device_id e marca a ativação
        conn.execute(
            "UPDATE licenses SET device_id = ?, activated_at = ? WHERE code = ?",
            (device_id, datetime.utcnow().isoformat(), code)
        )
        conn.commit()

    days_left = (expires_at - datetime.utcnow()).days
    return jsonify({
        "ok": True,
        "email": email,
        "expires_at": expires_at.isoformat(),
        "days_left": days_left,
        "message": f"Licença ativa! Restam {days_left} dias."
    }), 200

# ==============================================================
# ENDPOINT DE VERIFICAÇÃO (chamado a cada inicialização do app)
# ==============================================================

@app.route("/verify", methods=["POST"])
def verify_license():
    """
    Verifica se um código ainda está ativo (sem re-ativar).
    Chamado na inicialização do app para validação online contínua.
    Body JSON: { "code": "PXPRO-...", "device_id": "..." }
    """
    api_key = request.headers.get("X-API-Key", "")
    if api_key != ACTIVATION_API_KEY:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    body      = request.get_json(force=True) or {}
    code      = str(body.get("code", "")).strip().upper()
    device_id = str(body.get("device_id", "")).strip()

    with get_db() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE code = ?", (code,)).fetchone()

    if not row:
        return jsonify({"ok": False, "error": "Código não encontrado."}), 404

    if row["status"] != "active":
        return jsonify({"ok": False, "error": "Licença inativa."}), 403

    if row["device_id"] and row["device_id"] != device_id:
        return jsonify({"ok": False, "error": "Dispositivo não autorizado."}), 403

    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.utcnow() > expires_at:
        return jsonify({"ok": False, "error": "Licença expirada."}), 403

    days_left = (expires_at - datetime.utcnow()).days
    return jsonify({"ok": True, "days_left": days_left, "email": row["email"]}), 200

# ==============================================================
# ENDPOINT ADMIN — Gera licença manual
# ==============================================================

@app.route("/admin/generate", methods=["POST"])
def admin_generate():
    """
    Gera uma licença manualmente (para cortesias, testes, reembolsos, etc.).
    Protegido pela ACTIVATION_API_KEY.
    Body JSON: { "email": "...", "days": 30 }
    """
    api_key = request.headers.get("X-API-Key", "")
    if api_key != ACTIVATION_API_KEY:
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    body  = request.get_json(force=True) or {}
    email = str(body.get("email", "")).strip().lower()
    days  = int(body.get("days", LICENSE_DAYS))

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Email inválido."}), 400

    code = create_license(email=email, ckato_order="MANUAL", days=days)

    with get_db() as conn:
        row = conn.execute("SELECT expires_at FROM licenses WHERE code = ?", (code,)).fetchone()
        expires_at = row["expires_at"] if row else ""

    send_activation_email(email, code, expires_at)

    return jsonify({"ok": True, "code": code, "email": email, "days": days}), 200

# ==============================================================
# ENDPOINT DE SAÚDE
# ==============================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()}), 200

# ==============================================================
# INICIALIZAÇÃO
# ==============================================================

init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[SERVER] Iniciando na porta {port}...")
    app.run(host="0.0.0.0", port=port, debug=False)

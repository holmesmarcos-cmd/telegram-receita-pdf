import os
import base64
import logging
from io import BytesIO

import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("rxbot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "").strip()
APPS_SCRIPT_TOKEN = os.getenv("APPS_SCRIPT_TOKEN", "").strip()

# Render will set PORT and you set RENDER_EXTERNAL_URL after deploy
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip()
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("Falta BOT_TOKEN (BotFather).")
if not APPS_SCRIPT_URL or not APPS_SCRIPT_TOKEN:
    raise RuntimeError("Falta APPS_SCRIPT_URL e/ou APPS_SCRIPT_TOKEN (Apps Script Web App).")

# =========================
# STATES
# =========================
(
    PACIENTE,
    QTD_MEDS,
    MED_DOSE_1, N_CAIXAS_1, POSOLOGIA_1,
    MED_DOSE_2, N_CAIXAS_2, POSOLOGIA_2,
    MED_DOSE_3, N_CAIXAS_3, POSOLOGIA_3,
    CONFIRMA,
) = range(12)


def clean(text: str) -> str:
    return " ".join((text or "").strip().split())


def get_qtd(context) -> int:
    return int(context.user_data.get("qtd_meds", 1))


def summary_text(context) -> str:
    p = context.user_data.get("paciente", "")
    qtd = get_qtd(context)

    lines = [f"*CONFIRMAR RECEITA (1–3 medicamentos)*\n", f"*Paciente:* {p}\n"]
    for i in range(1, qtd + 1):
        md = context.user_data.get(f"med_dose_{i}", "")
        nc = context.user_data.get(f"n_caixas_{i}", "")
        pos = context.user_data.get(f"posologia_{i}", "")
        lines.append(f"*Medicamento {i}:* {md}")
        lines.append(f"*Nº de caixas {i}:* {nc}")
        lines.append(f"*Posologia {i}:* {pos}\n")

    lines.append("Responda:\n✅ *SIM* para gerar o PDF\n❌ *NÃO* para cancelar")
    return "\n".join(lines)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Vamos gerar a receita em PDF.\n\n"
        "1) Digite o *NOME COMPLETO do paciente*:",
        parse_mode=ParseMode.MARKDOWN,
    )
    return PACIENTE


async def get_paciente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["paciente"] = clean(update.message.text)
    await update.message.reply_text(
        "2) Quantos medicamentos na receita? (digite 1, 2 ou 3)",
    )
    return QTD_MEDS


async def get_qtd_meds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = clean(update.message.text)
    if t not in ("1", "2", "3"):
        await update.message.reply_text("Por favor, digite apenas: 1, 2 ou 3.")
        return QTD_MEDS

    context.user_data["qtd_meds"] = int(t)

    await update.message.reply_text(
        "3) Medicamento 1 + dosagem (ex: DEXILANT 30MG):"
    )
    return MED_DOSE_1


# ---------- MED 1 ----------
async def med1_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["med_dose_1"] = clean(update.message.text)
    await update.message.reply_text("4) Nº de caixas 1 (ex: 01 CAIXA / 01 FRASCO):")
    return N_CAIXAS_1


async def med1_caixas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["n_caixas_1"] = clean(update.message.text)
    await update.message.reply_text("5) Posologia 1:")
    return POSOLOGIA_1


async def med1_posologia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["posologia_1"] = clean(update.message.text)

    qtd = get_qtd(context)
    if qtd >= 2:
        await update.message.reply_text("6) Medicamento 2 + dosagem:")
        return MED_DOSE_2

    # preencher 2 e 3 vazios para o Apps Script
    for i in (2, 3):
        context.user_data[f"med_dose_{i}"] = ""
        context.user_data[f"n_caixas_{i}"] = ""
        context.user_data[f"posologia_{i}"] = ""

    await update.message.reply_text(summary_text(context), parse_mode=ParseMode.MARKDOWN)
    return CONFIRMA


# ---------- MED 2 ----------
async def med2_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["med_dose_2"] = clean(update.message.text)
    await update.message.reply_text("7) Nº de caixas 2:")
    return N_CAIXAS_2


async def med2_caixas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["n_caixas_2"] = clean(update.message.text)
    await update.message.reply_text("8) Posologia 2:")
    return POSOLOGIA_2


async def med2_posologia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["posologia_2"] = clean(update.message.text)

    qtd = get_qtd(context)
    if qtd >= 3:
        await update.message.reply_text("9) Medicamento 3 + dosagem:")
        return MED_DOSE_3

    # preencher 3 vazio
    context.user_data["med_dose_3"] = ""
    context.user_data["n_caixas_3"] = ""
    context.user_data["posologia_3"] = ""

    await update.message.reply_text(summary_text(context), parse_mode=ParseMode.MARKDOWN)
    return CONFIRMA


# ---------- MED 3 ----------
async def med3_dose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["med_dose_3"] = clean(update.message.text)
    await update.message.reply_text("10) Nº de caixas 3:")
    return N_CAIXAS_3


async def med3_caixas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["n_caixas_3"] = clean(update.message.text)
    await update.message.reply_text("11) Posologia 3:")
    return POSOLOGIA_3


async def med3_posologia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["posologia_3"] = clean(update.message.text)
    await update.message.reply_text(summary_text(context), parse_mode=ParseMode.MARKDOWN)
    return CONFIRMA


# ---------- CONFIRM ----------
async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = clean(update.message.text).upper()

    if ans not in ("SIM", "NÃO", "NAO"):
        await update.message.reply_text("Responda apenas *SIM* ou *NÃO*.", parse_mode=ParseMode.MARKDOWN)
        return CONFIRMA

    if ans in ("NÃO", "NAO"):
        await update.message.reply_text("Cancelado. Para começar de novo, digite /start")
        context.user_data.clear()
        return ConversationHandler.END

    # Build payload expected by Apps Script
    payload = {
        "token": APPS_SCRIPT_TOKEN,
        "paciente": context.user_data.get("paciente", ""),
        "med1": {
            "dose": context.user_data.get("med_dose_1", ""),
            "caixas": context.user_data.get("n_caixas_1", ""),
            "posologia": context.user_data.get("posologia_1", ""),
        },
        "med2": {
            "dose": context.user_data.get("med_dose_2", ""),
            "caixas": context.user_data.get("n_caixas_2", ""),
            "posologia": context.user_data.get("posologia_2", ""),
        },
        "med3": {
            "dose": context.user_data.get("med_dose_3", ""),
            "caixas": context.user_data.get("n_caixas_3", ""),
            "posologia": context.user_data.get("posologia_3", ""),
        },
    }

    await update.message.reply_text("Gerando PDF…")

    try:
        r = requests.post(APPS_SCRIPT_URL, json=payload, timeout=90)
        data = r.json()
    except Exception as e:
        log.exception("Erro chamando Apps Script")
        await update.message.reply_text(f"Falha ao chamar Apps Script. Detalhe: {e}")
        context.user_data.clear()
        return ConversationHandler.END

    if not data.get("ok"):
        await update.message.reply_text(f"Apps Script retornou erro: {data}")
        context.user_data.clear()
        return ConversationHandler.END

    b64 = data.get("base64", "")
    filename = data.get("filename", "receita.pdf")

    try:
        pdf_bytes = base64.b64decode(b64)
    except Exception:
        await update.message.reply_text("Não consegui decodificar o PDF retornado.")
        context.user_data.clear()
        return ConversationHandler.END

    bio = BytesIO(pdf_bytes)
    bio.name = filename
    bio.seek(0)

    await update.message.reply_document(document=bio, filename=filename, caption="Receita em PDF")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Ok, cancelado. Para começar de novo, digite /start")
    return ConversationHandler.END


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("OK")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PACIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_paciente)],
            QTD_MEDS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_qtd_meds)],

            MED_DOSE_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, med1_dose)],
            N_CAIXAS_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, med1_caixas)],
            POSOLOGIA_1: [MessageHandler(filters.TEXT & ~filters.COMMAND, med1_posologia)],

            MED_DOSE_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, med2_dose)],
            N_CAIXAS_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, med2_caixas)],
            POSOLOGIA_2: [MessageHandler(filters.TEXT & ~filters.COMMAND, med2_posologia)],

            MED_DOSE_3: [MessageHandler(filters.TEXT & ~filters.COMMAND, med3_dose)],
            N_CAIXAS_3: [MessageHandler(filters.TEXT & ~filters.COMMAND, med3_caixas)],
            POSOLOGIA_3: [MessageHandler(filters.TEXT & ~filters.COMMAND, med3_posologia)],

            CONFIRMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("health", health))

    # Webhook mode (recommended for Render)
    if RENDER_EXTERNAL_URL:
        webhook_url = f"{RENDER_EXTERNAL_URL}/webhook"
        log.info("Setting webhook: %s", webhook_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="webhook",
            webhook_url=webhook_url,
        )
    else:
        # If you prefer local tests
        app.run_polling()

if __name__ == "__main__":
    main()

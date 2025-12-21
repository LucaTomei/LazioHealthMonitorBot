# 🚀 Quick Start - Docker Run

Avvia il bot in **30 secondi** con un singolo comando!

## ⚡ Setup Ultra-Rapido

### 1. Solo il Token (Dati NON Persistenti)

```bash
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

✅ Fatto! Il bot è attivo.
⚠️ **ATTENZIONE**: I dati si perdono se rimuovi il container.

---

### 2. Con Persistenza Dati (RACCOMANDATO)

```bash
# Crea directory locale
mkdir -p ~/lazio-bot-data

# Avvia con volume persistente
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI \
  -v ~/lazio-bot-data:/app/data \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

✅ I dati persistono tra riavvii del container!

---

### 3. Setup Completo con Tutti i Volumi

```bash
# Crea tutte le directory
mkdir -p ~/lazio-bot/{data,logs,reports_pdf,prenotazioni_pdf}

# Avvia con tutti i volumi
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI \
  -e SERVER_NAME=raspberry-casa \
  -e LOG_LEVEL=INFO \
  -v ~/lazio-bot/data:/app/data \
  -v ~/lazio-bot/logs:/app/logs \
  -v ~/lazio-bot/reports_pdf:/app/reports_pdf \
  -v ~/lazio-bot/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

✅ Setup completo con:
- Dati persistenti
- Log accessibili
- PDF salvati localmente
- Configurazione personalizzata

---

## 🎯 Configurazione

### Variabili d'Ambiente Disponibili

| Variabile | Richiesta | Default | Descrizione |
|-----------|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ Sì | - | Token del bot Telegram |
| `SERVER_NAME` | No | `server1` | Nome identificativo |
| `LOG_LEVEL` | No | `INFO` | DEBUG, INFO, WARNING, ERROR |
| `CHECK_INTERVAL` | No | `300` | Intervallo controlli (secondi) |
| `TZ` | No | `Europe/Rome` | Timezone |

### Esempio con Tutte le Variabili

```bash
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=123456789:ABC... \
  -e SERVER_NAME=mio-raspberry \
  -e LOG_LEVEL=DEBUG \
  -e CHECK_INTERVAL=600 \
  -e TZ=Europe/Rome \
  -v ~/lazio-bot/data:/app/data \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

---

## 📋 Comandi Utili

```bash
# Visualizza log in tempo reale
docker logs -f lazio-health-bot

# Ferma il bot
docker stop lazio-health-bot

# Avvia il bot (se fermo)
docker start lazio-health-bot

# Riavvia il bot
docker restart lazio-health-bot

# Rimuovi il bot
docker rm -f lazio-health-bot

# Aggiorna all'ultima versione
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest
docker rm -f lazio-health-bot
# Poi riesegui il comando docker run
```

---

## 🔍 Verifica Funzionamento

```bash
# Controlla che sia in esecuzione
docker ps | grep lazio-health-bot

# Visualizza output iniziale
docker logs lazio-health-bot

# Output atteso:
# === Lazio Health Monitor Bot Entrypoint ===
# ✓ TELEGRAM_BOT_TOKEN is set
# ✓ Directory setup complete
# ✓ Configuration files ready
# Starting bot as botuser...
# INFO - Inizializzazione bot su server: ...
# INFO - Token Telegram caricato correttamente
```

---

## 🎮 Primo Utilizzo

1. **Avvia il container** con uno dei comandi sopra
2. **Apri Telegram** e cerca il tuo bot
3. **Invia** `/start`
4. Sei automaticamente **admin** (primo utente!)
5. **Inizia a usare** il bot!

---

## 💡 Pro Tips

### Usa un File .env

```bash
# Crea file .env
cat > ~/lazio-bot.env << 'EOF'
TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI
SERVER_NAME=raspberry-pi
LOG_LEVEL=INFO
TZ=Europe/Rome
EOF

# Usa il file .env
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  --env-file ~/lazio-bot.env \
  -v ~/lazio-bot/data:/app/data \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

### Auto-Start al Boot

Il flag `--restart unless-stopped` fa sì che il container:
- ✅ Si riavvii automaticamente se crasha
- ✅ Si riavvii al boot del sistema
- ✅ NON si riavvii se tu lo fermi manualmente

---

## 🔄 Migrazione da Systemd

Se hai il bot con systemd:

```bash
# 1. Ferma systemd
sudo systemctl stop lazio-health-bot
sudo systemctl disable lazio-health-bot

# 2. Copia i dati
cp ~/.../authorized_users.json ~/lazio-bot/
cp ~/.../input_prescriptions.json ~/lazio-bot/

# 3. Monta i file nel container
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=... \
  -v ~/lazio-bot/authorized_users.json:/app/authorized_users.json \
  -v ~/lazio-bot/input_prescriptions.json:/app/input_prescriptions.json \
  -v ~/lazio-bot/data:/app/data \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

---

## 🆘 Troubleshooting

### Bot non parte

```bash
# Controlla i log
docker logs lazio-health-bot

# Errore comune: Token mancante
# Soluzione: Assicurati di aver passato -e TELEGRAM_BOT_TOKEN=...
```

### Permessi negati

```bash
# Dai permessi alla directory dati
chmod -R 777 ~/lazio-bot
```

### Container si ferma subito

```bash
# Vedi l'errore
docker logs lazio-health-bot

# Controlla che il token sia valido
docker run --rm \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest \
  python -c "import os; print('Token:', os.getenv('TELEGRAM_BOT_TOKEN')[:20]+'...')"
```

---

## 📚 Link Utili

- **Immagine Docker**: https://github.com/LucaTomei/LazioHealthMonitorBot/pkgs/container/laziohealthmonitorbot
- **Repository**: https://github.com/LucaTomei/LazioHealthMonitorBot
- **Documentazione Completa**: [docs/Installazione-Docker.md](Installazione-Docker.md)

---

## 🎉 Esempio Completo Raspberry Pi

```bash
# Setup completo su Raspberry Pi in 1 minuto

# 1. Crea directory
mkdir -p ~/lazio-bot/{data,logs,reports_pdf,prenotazioni_pdf}

# 2. Crea file .env
cat > ~/lazio-bot/.env << 'EOF'
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
SERVER_NAME=raspberry-casa
LOG_LEVEL=INFO
TZ=Europe/Rome
CHECK_INTERVAL=300
EOF

# 3. Avvia
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  --env-file ~/lazio-bot/.env \
  -v ~/lazio-bot/data:/app/data \
  -v ~/lazio-bot/logs:/app/logs \
  -v ~/lazio-bot/reports_pdf:/app/reports_pdf \
  -v ~/lazio-bot/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest

# 4. Verifica
docker logs -f lazio-health-bot

# 5. Apri Telegram e invia /start
```

✅ **FATTO!** Il bot è attivo e funzionante! 🎊

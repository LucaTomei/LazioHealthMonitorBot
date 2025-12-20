# 🏥 Lazio Health Monitor Bot - Guida Installazione

## 📋 Requisiti

- **Raspberry Pi** (qualsiasi modello con Docker) o **PC Linux/Windows/Mac**
- **Docker** installato
- **Token Telegram Bot** (ottienilo da [@BotFather](https://t.me/BotFather))
- 10 minuti di tempo

---

## 🚀 Installazione Veloce (3 Passi)

### STEP 1: Installa Docker

#### Su Raspberry Pi / Linux:
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

Poi **riavvia** o fai logout/login.

#### Su Windows:
Scarica [Docker Desktop](https://www.docker.com/products/docker-desktop)

#### Su Mac:
Scarica [Docker Desktop per Mac](https://www.docker.com/products/docker-desktop)

---

### STEP 2: Configura il Bot

```bash
# Crea directory per il bot
mkdir -p ~/lazio-health-bot
cd ~/lazio-health-bot

# Crea file di configurazione
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI
SERVER_NAME=mio-bot
LOG_LEVEL=INFO
TZ=Europe/Rome
EOF

# Crea file utenti autorizzati
cat > authorized_users.json << 'EOF'
[
  "123456789"
]
EOF

# Crea file prescrizioni (vuoto per iniziare)
cat > input_prescriptions.json << 'EOF'
[]
EOF
```

**Importante**: 
1. Sostituisci `IL_TUO_TOKEN_QUI` con il tuo token da @BotFather
2. Sostituisci `123456789` con il tuo Telegram User ID

#### Come ottenere il tuo Telegram User ID:
1. Apri Telegram
2. Cerca [@userinfobot](https://t.me/userinfobot)
3. Invia `/start`
4. Il bot ti dirà il tuo ID

---

### STEP 3: Avvia il Bot

```bash
# Pull dell'immagine Docker
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest

# Avvia il bot
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/authorized_users.json:/app/authorized_users.json \
  -v $(pwd)/input_prescriptions.json:/app/input_prescriptions.json \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/reports_pdf:/app/reports_pdf \
  -v $(pwd)/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest

# Verifica che funzioni
docker logs -f lazio-health-bot
```

**Output corretto**:
```
INFO - Inizializzazione bot su server: mio-bot
INFO - Token Telegram caricato correttamente
INFO - Sistema multi-processo avviato
```

Premi `Ctrl+C` per uscire dai logs.

---

## 🎉 Fatto! Testa il Bot

1. Apri Telegram
2. Cerca il tuo bot
3. Invia `/start`
4. Dovresti ricevere il menu principale! 🎊

---

## 🔧 Comandi Utili

### Visualizza logs
```bash
docker logs lazio-health-bot
```

### Ferma il bot
```bash
docker stop lazio-health-bot
```

### Riavvia il bot
```bash
docker restart lazio-health-bot
```

### Aggiorna all'ultima versione
```bash
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest
docker stop lazio-health-bot
docker rm lazio-health-bot
# Poi riesegui il comando "docker run" dello STEP 3
```

### Rimuovi il bot
```bash
docker stop lazio-health-bot
docker rm lazio-health-bot
```

---

## 📁 Struttura Directory

```
~/lazio-health-bot/
├── .env                        ← Configurazione (TOKEN!)
├── authorized_users.json       ← Utenti autorizzati
├── input_prescriptions.json    ← Le tue prescrizioni
├── logs/                       ← Log del bot
├── data/                       ← Cache dati
├── reports_pdf/                ← Referti scaricati
└── prenotazioni_pdf/           ← PDF conferme prenotazioni
```

---

## ⚙️ Configurazione Avanzata

### Aggiungi altri utenti autorizzati

Modifica `authorized_users.json`:
```json
[
  "123456789",
  "987654321",
  "555666777"
]
```

Poi riavvia: `docker restart lazio-health-bot`

### Cambia livello di log

Modifica `.env`:
```
LOG_LEVEL=DEBUG
```

Poi riavvia: `docker restart lazio-health-bot`

### Multi-server setup

Su ogni server, usa un nome diverso:
```
SERVER_NAME=raspberry-casa
SERVER_NAME=pc-ufficio
SERVER_NAME=server-cloud
```

---

## 🆘 Problemi Comuni

### Bot non risponde
```bash
# Verifica che sia in esecuzione
docker ps | grep lazio-health-bot

# Controlla i log
docker logs lazio-health-bot --tail 50
```

### "Token non valido"
- Verifica che il token nel file `.env` sia corretto
- Genera un nuovo token con @BotFather se necessario

### "Utente non autorizzato"
- Verifica che il tuo User ID sia in `authorized_users.json`
- Riavvia dopo aver modificato: `docker restart lazio-health-bot`

### Immagine non trovata
```bash
# Verifica che Docker possa scaricare l'immagine
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest

# Se privata, fai login (non necessario se pubblica)
echo "YOUR_GITHUB_PAT" | docker login ghcr.io -u LucaTomei --password-stdin
```

---

## 🔄 Backup e Ripristino

### Backup
```bash
cd ~/lazio-health-bot
tar -czf backup-$(date +%Y%m%d).tar.gz .env authorized_users.json input_prescriptions.json data/
```

### Ripristino
```bash
cd ~/lazio-health-bot
tar -xzf backup-20241209.tar.gz
docker restart lazio-health-bot
```

---

## 📊 Monitoraggio

### Uso risorse
```bash
docker stats lazio-health-bot
```

### Spazio disco
```bash
du -sh ~/lazio-health-bot/
```

---

## 🎯 Versioni Disponibili

- `latest` - Ultima versione stabile (consigliata)
- `v1.0.0` - Versione specifica
- `develop` - Versione di sviluppo (test)

Per usare una versione specifica:
```bash
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0
```

---

## 💡 Tips

1. **Backup regolari**: Fai backup settimanali
2. **Aggiornamenti**: Controlla aggiornamenti ogni mese
3. **Logs**: Pulisci i log vecchi periodicamente
4. **Monitoraggio**: Usa `docker logs` per verificare lo stato

---

## 🔗 Link Utili

- **Repository**: https://github.com/LucaTomei/LazioHealthMonitorBot
- **Issues**: https://github.com/LucaTomei/LazioHealthMonitorBot/issues
- **Docker Image**: https://github.com/LucaTomei/LazioHealthMonitorBot/pkgs/container/laziohealthmonitorbot

---

## 📞 Supporto

Problemi? Apri una issue su GitHub:
https://github.com/LucaTomei/LazioHealthMonitorBot/issues

---

**Versione Guida**: 1.0  
**Ultimo Aggiornamento**: Dicembre 2025  
**Autore**: Luca Tomei
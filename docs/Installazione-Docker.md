# 🐳 Installazione con Docker - Guida Completa

Questa guida ti aiuterà a installare e configurare il **Lazio Health Monitor Bot** utilizzando Docker. Docker semplifica l'installazione eliminando problemi di dipendenze e garantendo un ambiente di esecuzione isolato e consistente.

## 📋 Indice

- [Prerequisiti](#-prerequisiti)
- [Installazione Docker](#-installazione-docker)
- [Metodo 1: Utilizzo con Docker Compose (Raccomandato)](#-metodo-1-utilizzo-con-docker-compose-raccomandato)
- [Metodo 2: Utilizzo con Docker Run](#-metodo-2-utilizzo-con-docker-run)
- [Configurazione](#-configurazione)
- [Gestione del Container](#-gestione-del-container)
- [Verifica del Funzionamento](#-verifica-del-funzionamento)
- [Monitoraggio e Logs](#-monitoraggio-e-logs)
- [Backup e Ripristino](#-backup-e-ripristino)
- [Aggiornamenti](#-aggiornamenti)
- [Risoluzione Problemi](#-risoluzione-problemi)
- [Configurazioni Avanzate](#-configurazioni-avanzate)

---

## 🎯 Prerequisiti

### Hardware Minimo
- **RAM**: Minimo 256MB, raccomandato 512MB
- **Storage**: Minimo 500MB di spazio libero
- **CPU**: Qualsiasi architettura supportata da Docker (amd64, arm64, armv7)

### Software Richiesto
- **Docker** versione 20.10 o superiore
- **Docker Compose** versione 1.29 o superiore (opzionale ma raccomandato)
- Connessione internet per il download dell'immagine

### Informazioni Necessarie
- **Token Telegram Bot**: Ottenibile da [@BotFather](https://t.me/BotFather)
- **Telegram User ID**: Ottenibile da [@userinfobot](https://t.me/userinfobot)

---

## 🔧 Installazione Docker

### Su Raspberry Pi / Linux (Debian/Ubuntu)

```bash
# Installazione automatica Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Aggiungi il tuo utente al gruppo docker per evitare sudo
sudo usermod -aG docker $USER

# Applica le modifiche (logout/login o riavvia)
newgrp docker

# Verifica installazione
docker --version
docker compose version
```

### Su Raspberry Pi OS (Raspbian)

```bash
# Il metodo sopra funziona anche per Raspberry Pi OS
# Se hai problemi con architetture ARM, verifica:
uname -m  # Dovrebbe mostrare armv7l, aarch64, etc.

# Docker è già ottimizzato per ARM
```

### Su Windows

1. Scarica [Docker Desktop per Windows](https://www.docker.com/products/docker-desktop)
2. Esegui l'installer e segui le istruzioni
3. Riavvia il computer quando richiesto
4. Apri Docker Desktop e attendi l'avvio

### Su macOS

1. Scarica [Docker Desktop per Mac](https://www.docker.com/products/docker-desktop)
2. Trascina Docker.app nella cartella Applicazioni
3. Avvia Docker dalla cartella Applicazioni
4. Attendi che Docker si avvii completamente

---

## 🚀 Metodo 1: Utilizzo con Docker Compose (Raccomandato)

Docker Compose semplifica la gestione del container e dei suoi parametri.

### Passo 1: Prepara la Directory di Lavoro

```bash
# Crea una directory dedicata
mkdir -p ~/lazio-health-bot
cd ~/lazio-health-bot

# Scarica il docker-compose.yml
# Se hai clonato la repository:
git clone https://github.com/LucaTomei/LazioHealthMonitorBot.git
cd LazioHealthMonitorBot

# Oppure scarica solo il file docker-compose:
curl -O https://raw.githubusercontent.com/LucaTomei/LazioHealthMonitorBot/main/docker-compose.ghcr.yml
mv docker-compose.ghcr.yml docker-compose.yml
```

### Passo 2: Configura le Variabili d'Ambiente

Crea il file `.env` con le tue configurazioni:

```bash
cat > .env << 'EOF'
# ============================================
# TELEGRAM BOT CONFIGURATION
# ============================================
TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI

# ============================================
# API CONFIGURATION (Non modificare se non necessario)
# ============================================
BASE_URL=https://recup-webapi-appmobile.regione.lazio.it
AUTH_HEADER=Basic QVBQTU9CSUxFX1NQRUNJQUw6UGs3alVTcDgzbUh4VDU4NA==

# ============================================
# APPLICATION SETTINGS
# ============================================
SERVER_NAME=raspberry-casa
LOG_LEVEL=INFO
TZ=Europe/Rome

# ============================================
# MONITORING SETTINGS
# ============================================
CHECK_INTERVAL=300
ENABLE_NOTIFICATIONS=true

# ============================================
# ADVANCED SETTINGS (Opzionali)
# ============================================
MAX_RETRIES=3
REQUEST_TIMEOUT=30
DEBUG_MODE=false
EOF
```

**⚠️ IMPORTANTE**: Sostituisci `IL_TUO_TOKEN_QUI` con il tuo token ottenuto da @BotFather!

### Passo 3: Crea i File di Configurazione

```bash
# File utenti autorizzati (sostituisci 123456789 con il tuo User ID)
cat > authorized_users.json << 'EOF'
[
  "123456789"
]
EOF

# File prescrizioni (inizialmente vuoto)
cat > input_prescriptions.json << 'EOF'
[]
EOF

# Crea le directory necessarie
mkdir -p logs data reports_pdf prenotazioni_pdf debug_responses
```

### Passo 4: Avvia il Bot con Docker Compose

```bash
# Scarica l'immagine Docker
docker compose pull

# Avvia il bot in background
docker compose up -d

# Verifica che il container sia in esecuzione
docker compose ps
```

Output atteso:
```
NAME                       IMAGE                                          STATUS
telegram-monitoring-bot    ghcr.io/lucatomei/laziohealthmonitorbot:latest Up 10 seconds
```

### Passo 5: Verifica i Log

```bash
# Visualizza i log in tempo reale
docker compose logs -f

# Dovresti vedere:
# INFO - Inizializzazione bot su server: raspberry-casa
# INFO - Token Telegram caricato correttamente
# INFO - Sistema multi-processo avviato
```

Premi `Ctrl+C` per uscire dalla visualizzazione dei log.

---

## 🔨 Metodo 2: Utilizzo con Docker Run

Se preferisci non usare Docker Compose, puoi avviare il bot con `docker run`.

### Passo 1: Prepara la Directory di Lavoro

```bash
# Crea directory e file di configurazione
mkdir -p ~/lazio-health-bot
cd ~/lazio-health-bot

# Crea il file .env (come nel Metodo 1)
cat > .env << 'EOF'
TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI
SERVER_NAME=raspberry-casa
LOG_LEVEL=INFO
TZ=Europe/Rome
CHECK_INTERVAL=300
ENABLE_NOTIFICATIONS=true
EOF

# Crea file configurazione
cat > authorized_users.json << 'EOF'
["123456789"]
EOF

cat > input_prescriptions.json << 'EOF'
[]
EOF

# Crea directory
mkdir -p logs data reports_pdf prenotazioni_pdf debug_responses
```

### Passo 2: Scarica l'Immagine Docker

```bash
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

### Passo 3: Avvia il Container

```bash
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
  -v $(pwd)/debug_responses:/app/debug_responses \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

### Passo 4: Verifica il Container

```bash
# Verifica che sia in esecuzione
docker ps | grep lazio-health-bot

# Visualizza i log
docker logs -f lazio-health-bot
```

---

## ⚙️ Configurazione

### Variabili d'Ambiente Principali

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | **OBBLIGATORIO** | Token del bot Telegram |
| `SERVER_NAME` | `server1` | Nome identificativo del server (utile per multi-server) |
| `LOG_LEVEL` | `INFO` | Livello di logging: DEBUG, INFO, WARNING, ERROR, CRITICAL |
| `TZ` | `Europe/Rome` | Timezone per i log e le notifiche |
| `CHECK_INTERVAL` | `300` | Intervallo di verifica in secondi (300 = 5 minuti) |
| `ENABLE_NOTIFICATIONS` | `true` | Abilita/disabilita le notifiche automatiche |
| `DEBUG_MODE` | `false` | Modalità debug per troubleshooting |

### Percorsi delle Directory

| Directory Host | Directory Container | Scopo |
|----------------|---------------------|-------|
| `./logs` | `/app/logs` | File di log con rotazione automatica |
| `./data` | `/app/data` | Cache dati e file temporanei |
| `./reports_pdf` | `/app/reports_pdf` | PDF dei referti medici scaricati |
| `./prenotazioni_pdf` | `/app/prenotazioni_pdf` | PDF delle conferme di prenotazione |
| `./debug_responses` | `/app/debug_responses` | Risposte API per debugging |

### File di Configurazione

| File | Scopo |
|------|-------|
| `authorized_users.json` | Lista degli User ID Telegram autorizzati |
| `input_prescriptions.json` | Prescrizioni monitorate dal bot |
| `.env` | Variabili d'ambiente e configurazione |

---

## 🎮 Gestione del Container

### Con Docker Compose

```bash
# Avvia il bot
docker compose up -d

# Ferma il bot
docker compose down

# Riavvia il bot
docker compose restart

# Visualizza lo stato
docker compose ps

# Visualizza i log
docker compose logs -f

# Visualizza solo gli ultimi 100 log
docker compose logs --tail 100

# Ferma e rimuovi tutto (ATTENZIONE: non cancella i dati nei volumi)
docker compose down --volumes
```

### Con Docker Run

```bash
# Avvia il container (se fermato)
docker start lazio-health-bot

# Ferma il container
docker stop lazio-health-bot

# Riavvia il container
docker restart lazio-health-bot

# Visualizza lo stato
docker ps -a | grep lazio-health-bot

# Visualizza i log
docker logs -f lazio-health-bot

# Rimuovi il container (i dati nei volumi rimangono)
docker rm lazio-health-bot

# Rimuovi il container forzatamente (anche se in esecuzione)
docker rm -f lazio-health-bot
```

---

## ✅ Verifica del Funzionamento

### 1. Verifica Container in Esecuzione

```bash
# Con Docker Compose
docker compose ps

# Con Docker Run
docker ps | grep lazio-health-bot
```

Dovresti vedere lo stato `Up` o `running`.

### 2. Verifica Log

```bash
# Con Docker Compose
docker compose logs --tail 50

# Con Docker Run
docker logs --tail 50 lazio-health-bot
```

Cerca questi messaggi di successo:
```
INFO - Inizializzazione bot su server: ...
INFO - Token Telegram caricato correttamente
INFO - Sistema multi-processo avviato
```

### 3. Testa il Bot su Telegram

1. Apri Telegram
2. Cerca il tuo bot per nome
3. Invia il comando `/start`
4. Dovresti ricevere il messaggio di benvenuto e il menu principale

### 4. Verifica Salute del Container

```bash
# Con Docker Compose
docker compose ps

# Con Docker Run
docker inspect --format='{{.State.Health.Status}}' lazio-health-bot
```

Lo stato dovrebbe essere `healthy`.

---

## 📊 Monitoraggio e Logs

### Visualizzare i Log in Tempo Reale

```bash
# Con Docker Compose
docker compose logs -f

# Con Docker Run
docker logs -f lazio-health-bot

# Filtra solo gli errori
docker logs lazio-health-bot 2>&1 | grep ERROR

# Filtra per una parola chiave
docker logs lazio-health-bot 2>&1 | grep "prescrizione"
```

### Monitorare l'Utilizzo delle Risorse

```bash
# Statistiche in tempo reale
docker stats lazio-health-bot

# Output tipico:
# CONTAINER ID   NAME                  CPU %   MEM USAGE / LIMIT   MEM %
# abc123def456   lazio-health-bot     1.23%   128MiB / 512MiB     25.00%
```

### Accedere al Container

```bash
# Apri una shell nel container (utile per debugging)
docker exec -it lazio-health-bot /bin/sh

# Una volta dentro:
ls -la /app
cat /app/logs/recup_monitor.log
exit
```

### Controllo File di Log

I log sono anche disponibili localmente:

```bash
cd ~/lazio-health-bot/logs
tail -f recup_monitor.log

# Visualizza solo gli errori
grep ERROR recup_monitor.log

# Conta quante volte appare una parola
grep -c "disponibilità" recup_monitor.log
```

---

## 💾 Backup e Ripristino

### Backup Completo

```bash
cd ~/lazio-health-bot

# Backup di tutti i dati importanti
tar -czf backup-$(date +%Y%m%d-%H%M%S).tar.gz \
  .env \
  authorized_users.json \
  input_prescriptions.json \
  data/ \
  logs/

# Verifica il backup
ls -lh backup-*.tar.gz
```

### Backup Solo Configurazione

```bash
# Backup solo configurazione (senza log)
tar -czf config-backup-$(date +%Y%m%d).tar.gz \
  .env \
  authorized_users.json \
  input_prescriptions.json
```

### Ripristino da Backup

```bash
cd ~/lazio-health-bot

# Ferma il bot
docker compose down  # oppure: docker stop lazio-health-bot

# Ripristina i file
tar -xzf backup-20241220-143022.tar.gz

# Riavvia il bot
docker compose up -d  # oppure: docker start lazio-health-bot
```

### Backup Automatico (Cron)

Crea un backup automatico ogni giorno alle 3:00 AM:

```bash
# Apri crontab
crontab -e

# Aggiungi questa riga:
0 3 * * * cd ~/lazio-health-bot && tar -czf ~/backups/lazio-bot-$(date +\%Y\%m\%d).tar.gz .env authorized_users.json input_prescriptions.json data/ && find ~/backups -name "lazio-bot-*.tar.gz" -mtime +30 -delete
```

---

## 🔄 Aggiornamenti

### Aggiornare all'Ultima Versione

#### Con Docker Compose

```bash
cd ~/lazio-health-bot

# 1. Scarica l'ultima versione
docker compose pull

# 2. Ricrea il container con la nuova immagine
docker compose up -d

# 3. Verifica la versione (controlla i log)
docker compose logs --tail 20
```

#### Con Docker Run

```bash
# 1. Scarica l'ultima immagine
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest

# 2. Ferma e rimuovi il vecchio container
docker stop lazio-health-bot
docker rm lazio-health-bot

# 3. Avvia il nuovo container (usa lo stesso comando del Metodo 2, Passo 3)
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
  -v $(pwd)/debug_responses:/app/debug_responses \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest

# 4. Verifica il funzionamento
docker logs -f lazio-health-bot
```

### Utilizzare Versioni Specifiche

```bash
# Lista tutte le versioni disponibili
docker search ghcr.io/lucatomei/laziohealthmonitorbot --limit 25

# Usa una versione specifica (esempio: v1.0.0)
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0

# Modifica docker-compose.yml per usare una versione specifica:
# image: ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0
```

### Rollback a Versione Precedente

Se l'aggiornamento causa problemi:

```bash
# 1. Identifica l'immagine precedente
docker images | grep laziohealthmonitorbot

# 2. Usa l'IMAGE ID della versione precedente
docker tag <OLD_IMAGE_ID> ghcr.io/lucatomei/laziohealthmonitorbot:latest

# 3. Riavvia il container
docker compose restart  # oppure: docker restart lazio-health-bot
```

---

## 🔧 Risoluzione Problemi

### Il Bot Non Si Avvia

**Problema**: Container si ferma immediatamente dopo l'avvio

```bash
# Verifica i log
docker logs lazio-health-bot

# Errori comuni:
```

**Errore**: `TELEGRAM_BOT_TOKEN non configurato`
```bash
# Verifica che .env contenga il token
cat .env | grep TELEGRAM_BOT_TOKEN

# Se manca, aggiungilo:
echo "TELEGRAM_BOT_TOKEN=il_tuo_token" >> .env

# Riavvia
docker compose restart
```

**Errore**: `Permission denied` sui file di configurazione
```bash
# Correggi i permessi
chmod 644 authorized_users.json input_prescriptions.json .env
chmod 755 logs data reports_pdf prenotazioni_pdf

# Riavvia
docker compose restart
```

### Il Bot Non Risponde su Telegram

**1. Verifica che il container sia attivo**
```bash
docker ps | grep lazio-health-bot
```

**2. Verifica i log per errori**
```bash
docker logs --tail 100 lazio-health-bot | grep ERROR
```

**3. Verifica la connessione a Telegram**
```bash
# Accedi al container
docker exec -it lazio-health-bot /bin/sh

# Testa la connessione
ping -c 3 api.telegram.org

# Esci
exit
```

**4. Verifica che il tuo User ID sia autorizzato**
```bash
cat authorized_users.json
# Deve contenere il tuo User ID
```

### Problemi di Memoria

**Problema**: Container si riavvia continuamente

```bash
# Verifica l'uso della memoria
docker stats lazio-health-bot

# Se supera il limite, aumentalo in docker-compose.yml:
# resources:
#   limits:
#     memory: 1024M  # Aumenta da 512M a 1024M
```

### Problemi di Rete

**Problema**: Errori di connessione alle API

```bash
# Verifica DNS nel container
docker exec lazio-health-bot ping -c 3 google.com

# Se fallisce, specifica DNS in docker-compose.yml:
# dns:
#   - 8.8.8.8
#   - 8.8.4.4
```

### File di Log Troppo Grandi

```bash
# Controlla dimensione log
du -sh ~/lazio-health-bot/logs

# Pulisci log vecchi (mantieni solo ultimi 7 giorni)
find ~/lazio-health-bot/logs -name "*.log.*" -mtime +7 -delete

# Oppure tronca il log corrente
> ~/lazio-health-bot/logs/recup_monitor.log
```

### Immagine Docker Non Trovata

**Errore**: `manifest unknown` o `not found`

```bash
# Verifica che l'immagine sia pubblica
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest

# Se l'immagine è privata, fai login:
echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u LucaTomei --password-stdin

# Poi riprova:
docker compose pull
```

### Debug Mode Avanzato

Se hai problemi persistenti:

```bash
# 1. Abilita debug mode nel .env
echo "DEBUG_MODE=true" >> .env
echo "LOG_LEVEL=DEBUG" >> .env

# 2. Riavvia il bot
docker compose restart

# 3. Visualizza log dettagliati
docker compose logs -f

# 4. Controlla anche debug_responses
ls -lah debug_responses/
```

---

## 🚀 Configurazioni Avanzate

### Multi-Server Setup

Esegui lo stesso bot su più server (es. Raspberry Pi a casa + VPS cloud):

**Server 1 (Raspberry Pi):**
```bash
# .env
SERVER_NAME=raspberry-casa
CHECK_INTERVAL=300
```

**Server 2 (VPS Cloud):**
```bash
# .env
SERVER_NAME=vps-cloud
CHECK_INTERVAL=300
```

Entrambi i server monitoreranno le stesse prescrizioni. Nei log vedrai da quale server arriva ogni notifica.

### Limitare Risorse su Raspberry Pi

Per Raspberry Pi con poca RAM:

```yaml
# docker-compose.yml
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 256M
    reservations:
      cpus: '0.1'
      memory: 64M
```

### Usare una Network Personalizzata

```yaml
# docker-compose.yml
networks:
  lazio-bot-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16

services:
  telegram-bot:
    networks:
      - lazio-bot-net
```

### Proxy e VPN

Se devi usare un proxy:

```yaml
# docker-compose.yml
environment:
  - HTTP_PROXY=http://proxy.example.com:8080
  - HTTPS_PROXY=http://proxy.example.com:8080
  - NO_PROXY=localhost,127.0.0.1
```

### Notifiche su Più Chat

Puoi configurare più utenti in `authorized_users.json`:

```json
[
  "123456789",
  "987654321",
  "555666777"
]
```

Ogni utente riceverà notifiche per le prescrizioni che aggiunge.

### Monitoraggio con Watchtower (Auto-Update)

Aggiorna automaticamente il bot quando esce una nuova versione:

```yaml
# Aggiungi al docker-compose.yml
services:
  watchtower:
    image: containrrr/watchtower
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - WATCHTOWER_CLEANUP=true
      - WATCHTOWER_POLL_INTERVAL=86400  # Controlla ogni 24h
    restart: unless-stopped
```

---

## 📚 Riferimenti

### Comandi Docker Utili

```bash
# Lista tutti i container (anche fermati)
docker ps -a

# Rimuovi tutti i container fermati
docker container prune

# Lista tutte le immagini
docker images

# Rimuovi immagini non utilizzate
docker image prune -a

# Spazio utilizzato da Docker
docker system df

# Pulisci tutto (ATTENZIONE!)
docker system prune -a --volumes
```

### Struttura File Completa

```
~/lazio-health-bot/
├── .env                           # Configurazione principale
├── docker-compose.yml             # Configurazione Docker Compose
├── authorized_users.json          # Utenti autorizzati
├── input_prescriptions.json       # Prescrizioni monitorate
├── logs/
│   ├── recup_monitor.log         # Log corrente
│   └── recup_monitor.log.1       # Log ruotati
├── data/
│   ├── previous_data.json        # Cache dati precedenti
│   └── reports_monitoring.json   # Monitoraggio referti
├── reports_pdf/                   # PDF referti scaricati
├── prenotazioni_pdf/              # PDF conferme prenotazioni
└── debug_responses/               # Risposte API (se DEBUG_MODE=true)
```

### Link Utili

- **Repository GitHub**: https://github.com/LucaTomei/LazioHealthMonitorBot
- **Docker Image**: https://github.com/LucaTomei/LazioHealthMonitorBot/pkgs/container/laziohealthmonitorbot
- **Issues & Supporto**: https://github.com/LucaTomei/LazioHealthMonitorBot/issues
- **Documentazione Docker**: https://docs.docker.com/
- **Docker Compose Reference**: https://docs.docker.com/compose/compose-file/

---

## 📞 Supporto

### Hai Problemi?

1. **Controlla i log**: `docker logs lazio-health-bot`
2. **Verifica la configurazione**: Assicurati che `.env` sia corretto
3. **Cerca tra le Issues**: https://github.com/LucaTomei/LazioHealthMonitorBot/issues
4. **Apri una nuova Issue**: Includi log e dettagli della tua configurazione

### Contribuire

Hai trovato un bug o vuoi suggerire un miglioramento?

1. Fork del repository
2. Crea un branch per la tua feature
3. Committa le modifiche
4. Apri una Pull Request

---

## 📜 Licenza

Questo progetto è rilasciato sotto licenza MIT.

---

**Autore**: Luca Tomei
**Ultima Modifica**: Dicembre 2024
**Versione Guida**: 1.0

---

⚠️ **Disclaimer**: Questo bot utilizza API non ufficiali del sistema RecUP della Regione Lazio. È stato creato per scopi personali ed educativi. L'utilizzo è a tuo rischio. L'autore non è responsabile per eventuali problemi derivanti dall'uso di questo software.

# Lazio Health Monitor Bot

Bot Telegram per monitorare automaticamente le disponibilità del Servizio Sanitario Nazionale nella Regione Lazio.

![Banner](https://img.shields.io/badge/Regione-Lazio-green)
![Python](https://img.shields.io/badge/Python-3.11-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)
![CI Validation](https://github.com/LucaTomei/LazioHealthMonitorBot/actions/workflows/ci-validation.yml/badge.svg)
![Docker Publish](https://github.com/LucaTomei/LazioHealthMonitorBot/actions/workflows/docker-publish.yml/badge.svg)
![Docker Image](https://img.shields.io/badge/docker-ghcr.io-blue)

## 🚀 Quick Start - Avvio in 30 Secondi

```bash
# Crea le directory necessarie
mkdir -p ~/lazio-bot/{data,logs,reports_pdf,prenotazioni_pdf}

# Avvia il container
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN_QUI \
  -v ~/lazio-bot/data:/app/data \
  -v ~/lazio-bot/logs:/app/logs \
  -v ~/lazio-bot/reports_pdf:/app/reports_pdf \
  -v ~/lazio-bot/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

**Fatto!** Apri Telegram, cerca il tuo bot e invia `/start`

---

## 📋 Caratteristiche

- 🔍 **Monitoraggio automatico** delle disponibilità ogni 5 minuti
- 🔔 **Notifiche intelligenti** per nuovi appuntamenti
- 📅 **Filtro date** per appuntamenti entro un periodo specifico
- 🚫 **Blacklist ospedali** per escludere strutture specifiche
- 🏥 **Prenotazione diretta** appuntamenti dal bot
- 🤖 **Prenotazione automatica** del primo slot disponibile
- 📝 **Gestione prenotazioni** attive e disdette
- 📄 **PDF conferme** prenotazioni e referti
- 👥 **Multi-utente** con sistema autorizzazioni
- 🗺️ **Geocoding ospedali** opzionale via Geoapify
- 🐳 **Auto-configurante** con Docker

---

## 🐳 Installazione Docker

### Metodo 1: Minimo (Test Veloce)

```bash
docker run -d \
  --name lazio-health-bot \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

⚠️ I dati non persistono al riavvio del container

### Metodo 2: Con Persistenza (RACCOMANDATO)

```bash
# Crea le directory
mkdir -p ~/lazio-bot/{data,logs,reports_pdf,prenotazioni_pdf}

# Avvia il container
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN \
  -v ~/lazio-bot/data:/app/data \
  -v ~/lazio-bot/logs:/app/logs \
  -v ~/lazio-bot/reports_pdf:/app/reports_pdf \
  -v ~/lazio-bot/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

✅ Il database SQLite in `data/recup_monitor.db` persiste tra riavvii

### Metodo 3: Setup Completo

```bash
# Crea le directory
mkdir -p ~/lazio-bot/{data,logs,reports_pdf,prenotazioni_pdf}

# Avvia il container con tutte le configurazioni
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN \
  -e SERVER_NAME=mio-server \
  -e LOG_LEVEL=INFO \
  -e GEOAPIFY_API_KEY=LA_TUA_CHIAVE \
  -v ~/lazio-bot/data:/app/data \
  -v ~/lazio-bot/logs:/app/logs \
  -v ~/lazio-bot/reports_pdf:/app/reports_pdf \
  -v ~/lazio-bot/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

✅ Configurazione completa con geocoding e log persistenti

---

## 🔧 Configurazione

### Ottenere il Token Telegram

1. Apri Telegram e cerca **@BotFather**
2. Invia `/newbot`
3. Segui le istruzioni
4. Salva il **token** fornito

### Ottenere il Tuo User ID

1. Cerca **@userinfobot** su Telegram
2. Invia `/start`
3. Salva il tuo **User ID**

### Variabili d'Ambiente

| Variabile | Obbligatoria | Default | Descrizione |
|-----------|--------------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ Sì | - | Token del bot |
| `SERVER_NAME` | No | `server1` | Nome server |
| `LOG_LEVEL` | No | `INFO` | Livello log (DEBUG, INFO, WARNING) |
| `CHECK_INTERVAL` | No | `300` | Intervallo controlli (secondi) |
| `TZ` | No | `Europe/Rome` | Timezone |
| `DB_FILE` | No | `data/recup_monitor.db` | Path del database SQLite |
| `GEOAPIFY_API_KEY` | No | - | API key per geocoding ospedali ([geoapify.com](https://www.geoapify.com)). Se assente il geocoding viene saltato silenziosamente. |

---

## 📱 Utilizzo

### Comandi Bot

Invia `/start` al bot e usa il menu:

- **➕ Aggiungi Prescrizione** - Monitora una nuova ricetta
- **📋 Lista Prescrizioni** - Vedi ricette monitorate
- **🔄 Verifica Disponibilità** - Controlla subito
- **🏥 Prenota** - Prenota un appuntamento
- **🤖 Prenota Automaticamente** - Auto-prenota primo slot
- **📝 Le mie Prenotazioni** - Gestisci prenotazioni
- **🔔 Gestisci Notifiche** - Attiva/disattiva notifiche
- **⏱ Imposta Filtro Date** - Filtra per periodo
- **🚫 Blacklist Ospedali** - Escludi strutture
- **📊 Configura Monitoraggio Referti** - Setup referti
- **ℹ️ Informazioni** - Info sul bot

### Primo Utilizzo

1. ✅ Avvia il container
2. 📱 Cerca il bot su Telegram
3. ✉️ Invia `/start`
4. 👑 Diventi admin automaticamente (primo utente)
5. ➕ Aggiungi la tua prima prescrizione

---

## 🔧 Gestione Container

```bash
# Visualizza log
docker logs -f lazio-health-bot

# Ferma
docker stop lazio-health-bot

# Avvia
docker start lazio-health-bot

# Riavvia
docker restart lazio-health-bot

# Rimuovi
docker rm -f lazio-health-bot

# Aggiorna
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest
docker rm -f lazio-health-bot
# Poi riesegui il comando docker run
```

---

## 🔄 Migrazione da Systemd (o da versione JSON)

Se hai il bot installato con systemd o una versione precedente che usava file JSON:

```bash
# 1. Ferma il vecchio bot
sudo systemctl stop lazio-health-bot
sudo systemctl disable lazio-health-bot

# 2. Prepara le directory
mkdir -p ~/lazio-bot/{data,logs,reports_pdf,prenotazioni_pdf}

# 3. Copia i vecchi file JSON nella root del bot
#    Il bot li migrerà automaticamente nel DB al primo avvio
cp /path/to/old/authorized_users.json ~/lazio-bot/
cp /path/to/old/input_prescriptions.json ~/lazio-bot/
cp /path/to/old/previous_data.json ~/lazio-bot/
cp /path/to/old/locations.json ~/lazio-bot/          # opzionale

# 4. Avvia con Docker
docker run -d \
  --name lazio-health-bot \
  --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN=IL_TUO_TOKEN \
  -v ~/lazio-bot/data:/app/data \
  -v ~/lazio-bot/logs:/app/logs \
  -v ~/lazio-bot/reports_pdf:/app/reports_pdf \
  -v ~/lazio-bot/prenotazioni_pdf:/app/prenotazioni_pdf \
  ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

Al primo avvio vedrai nei log la migrazione automatica:
```
Migrati X utenti da authorized_users.json
Migrate X prescrizioni da input_prescriptions.json
Migrati X record disponibilità da previous_data.json
Migrazione da JSON completata
```

Dopo la migrazione i file JSON non vengono più usati e possono essere eliminati.

---

## 🐛 Risoluzione Problemi

### Bot non parte

```bash
docker logs lazio-health-bot
```

**Errore comune**: `TELEGRAM_BOT_TOKEN is required`
- Soluzione: Aggiungi `-e TELEGRAM_BOT_TOKEN=...` al comando docker run

### Permission denied

```bash
chmod -R 777 ~/lazio-bot
```

### Container si ferma subito

Controlla i log per vedere l'errore:
```bash
docker logs lazio-health-bot
```

---

## 📚 Architettura

### Struttura Dati

```
~/lazio-bot/
├── data/
│   └── recup_monitor.db        # Database SQLite (unico file dati)
├── logs/
│   └── recup_monitor.log       # Log applicazione
├── reports_pdf/                 # Referti scaricati
└── prenotazioni_pdf/            # Conferme prenotazioni
```

> Il database viene creato automaticamente al primo avvio. Non è necessario creare file di configurazione manualmente.

### Container

- **Image**: `ghcr.io/lucatomei/laziohealthmonitorbot:latest`
- **User**: `botuser` (UID 1000, non-root per sicurezza)
- **Auto-configura**: Crea file mancanti all'avvio
- **Multi-arch**: Supporta amd64 e arm64 (Raspberry Pi)

---

## 🔒 Sicurezza

- ✅ Container non gira come root
- ✅ Token mai committato nel repository
- ✅ Auto-creazione file con permessi corretti
- ✅ Primo utente diventa admin automaticamente
- ✅ Sistema autorizzazioni multi-utente

---

## 🚀 Sviluppo

### Build Locale

```bash
git clone https://github.com/LucaTomei/LazioHealthMonitorBot.git
cd LazioHealthMonitorBot
docker build -t lazio-bot:local .
docker run -d -e TELEGRAM_BOT_TOKEN=... lazio-bot:local
```

### Struttura Codice

```
.
├── recup_monitor.py           # Main application
├── config.py                  # Configurazione
├── modules/                   # Moduli
│   ├── api_client.py         # API RecUP
│   ├── booking_client.py     # Prenotazioni
│   ├── bot_handlers.py       # Handler bot
│   ├── data_utils.py         # Gestione dati
│   ├── monitoring.py         # Monitoraggio
│   └── reports_client.py     # Referti
├── Dockerfile                 # Immagine Docker
└── docker-entrypoint.sh      # Script avvio
```

---

## 📖 Documentazione Avanzata

Per guide dettagliate:
- [docs/Installazione-Docker.md](docs/Installazione-Docker.md) - Guida completa Docker
- [docs/Migrazione-da-Systemd-a-Docker.md](docs/Migrazione-da-Systemd-a-Docker.md) - Migrazione systemd

---

## 🤝 Contribuire

1. Fork del repository
2. Crea branch: `git checkout -b feature/nuova-funzione`
3. Commit: `git commit -m "feat: descrizione"`
4. Push: `git push origin feature/nuova-funzione`
5. Apri Pull Request

---

## 📜 Licenza

MIT License - Vedi [LICENSE](LICENSE) per dettagli

---

## 📞 Supporto

- **Issues**: https://github.com/LucaTomei/LazioHealthMonitorBot/issues
- **Docker Image**: https://github.com/LucaTomei/LazioHealthMonitorBot/pkgs/container/laziohealthmonitorbot
- **CI/CD**: https://github.com/LucaTomei/LazioHealthMonitorBot/actions

---

## ⚠️ Disclaimer

Questo bot utilizza API non ufficiali del sistema RecUP della Regione Lazio. È stato creato per scopi personali ed educativi. L'utilizzo è a tuo rischio. L'autore non è responsabile per eventuali problemi derivanti dall'uso di questo software.

---

**Autore**: Luca Tomei
**Versione**: 1.0
**Ultimo Aggiornamento**: Dicembre 2024

# 🔄 Migrazione da Systemd a Docker

Guida per migrare il bot da un'installazione systemd (su Raspberry Pi) a Docker.

## 🎯 Perché Migrare a Docker?

### Vantaggi di Docker vs Systemd

| Aspetto | Systemd | Docker |
|---------|---------|--------|
| **Working Directory** | Può variare, causa problemi con path relativi | Sempre `/app`, nessun problema |
| **Dipendenze** | Gestite manualmente con pip | Incluse nell'immagine |
| **Aggiornamenti** | Manuale: git pull + pip install | `docker compose pull && docker compose up -d` |
| **Isolamento** | Condivide Python con sistema | Ambiente completamente isolato |
| **Portabilità** | Dipende da sistema operativo | Funziona ovunque giri Docker |
| **Configurazione** | File service systemd + script | Singolo file docker-compose.yml |
| **Logs** | systemd journal | Docker logs con rotazione automatica |
| **Backup** | Multipli file sparsi | Unica directory con volumi |

## 🐛 Problema Comune con Systemd

### Sintomi
- ✅ Il bot funziona
- ❌ I PDF finiscono nella directory sbagliata (spesso `/` o `/home/user`)
- ❌ I log non vengono creati dove previsto

### Causa
Il servizio systemd **non imposta la Working Directory** correttamente.

Esempio di servizio systemd **ERRATO**:
```ini
[Unit]
Description=Lazio Health Monitor Bot
After=network.target

[Service]
Type=simple
User=pi
ExecStart=/usr/bin/python3 /home/pi/LazioHealthMonitorBot/recup_monitor.py
Restart=always
# ❌ MANCA: WorkingDirectory

[Install]
WantedBy=multi-user.target
```

Esempio di servizio systemd **CORRETTO**:
```ini
[Unit]
Description=Lazio Health Monitor Bot
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/LazioHealthMonitorBot  # ✅ AGGIUNTO
ExecStart=/usr/bin/python3 /home/pi/LazioHealthMonitorBot/recup_monitor.py
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 📦 Procedura di Migrazione

### Step 0: Verifica Installazione Attuale

```bash
# Controlla se il servizio systemd esiste
sudo systemctl status lazio-health-bot

# Vedi dove vengono salvati i file
sudo journalctl -u lazio-health-bot -n 50 | grep -i pdf

# Trova i PDF sparsi
sudo find / -name "*booking*.pdf" 2>/dev/null
sudo find / -name "*referto*.pdf" 2>/dev/null
```

### Step 1: Backup Configurazione Attuale

```bash
# Crea directory di backup
mkdir -p ~/lazio-bot-backup
cd ~/lazio-bot-backup

# Backup file configurazione
cp ~/LazioHealthMonitorBot/.env . 2>/dev/null || echo "No .env file"
cp ~/LazioHealthMonitorBot/authorized_users.json .
cp ~/LazioHealthMonitorBot/input_prescriptions.json .
cp ~/LazioHealthMonitorBot/previous_data.json . 2>/dev/null || echo "No previous_data.json"
cp ~/LazioHealthMonitorBot/reports_monitoring.json . 2>/dev/null || echo "No reports_monitoring.json"

# Backup logs
cp -r ~/LazioHealthMonitorBot/logs . 2>/dev/null || echo "No logs directory"

# Backup dati
cp -r ~/LazioHealthMonitorBot/data . 2>/dev/null || echo "No data directory"

# Backup PDF (potrebbero essere in posti diversi!)
cp -r ~/LazioHealthMonitorBot/prenotazioni_pdf . 2>/dev/null || echo "No prenotazioni_pdf directory"
cp -r ~/LazioHealthMonitorBot/reports_pdf . 2>/dev/null || echo "No reports_pdf directory"

# Verifica backup
ls -la ~/lazio-bot-backup/
```

### Step 2: Ferma il Servizio Systemd

```bash
# Ferma il servizio
sudo systemctl stop lazio-health-bot

# Disabilita l'avvio automatico
sudo systemctl disable lazio-health-bot

# Verifica che sia fermo
sudo systemctl status lazio-health-bot
# Deve mostrare: Active: inactive (dead)
```

### Step 3: (Opzionale) Rimuovi Servizio Systemd

Se vuoi rimuovere completamente systemd:

```bash
# Rimuovi il file del servizio
sudo rm /etc/systemd/system/lazio-health-bot.service

# Ricarica systemd
sudo systemctl daemon-reload

# Verifica rimozione
sudo systemctl list-units | grep lazio
# Non deve mostrare nulla
```

### Step 4: Installa Docker

```bash
# Installa Docker (se non già installato)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Aggiungi utente al gruppo docker
sudo usermod -aG docker $USER

# Applica modifiche (logout/login o riavvia)
newgrp docker

# Verifica installazione
docker --version
docker compose version
```

### Step 5: Prepara Directory Docker

```bash
# Crea nuova directory per Docker
mkdir -p ~/lazio-health-bot
cd ~/lazio-health-bot

# Clona repository (per avere docker-compose.yml)
git clone https://github.com/LucaTomei/LazioHealthMonitorBot.git temp
cp temp/docker-compose.ghcr.yml ./docker-compose.yml
cp temp/.env.example ./.env
rm -rf temp

# Oppure scarica solo i file necessari
# curl -O https://raw.githubusercontent.com/LucaTomei/LazioHealthMonitorBot/main/docker-compose.ghcr.yml
# mv docker-compose.ghcr.yml docker-compose.yml
# curl -O https://raw.githubusercontent.com/LucaTomei/LazioHealthMonitorBot/main/.env.example
# mv .env.example .env
```

### Step 6: Ripristina Configurazione

```bash
cd ~/lazio-health-bot

# Ripristina file configurazione dal backup
cp ~/lazio-bot-backup/.env . 2>/dev/null || echo "Configura .env manualmente"
cp ~/lazio-bot-backup/authorized_users.json .
cp ~/lazio-bot-backup/input_prescriptions.json .

# Ripristina dati (opzionale, il bot ricrea automaticamente)
cp ~/lazio-bot-backup/previous_data.json ./data/ 2>/dev/null || true
cp ~/lazio-bot-backup/reports_monitoring.json . 2>/dev/null || true

# Crea directory necessarie
mkdir -p logs data reports_pdf prenotazioni_pdf debug_responses

# Ripristina PDF (se esistono)
cp -r ~/lazio-bot-backup/prenotazioni_pdf/* ./prenotazioni_pdf/ 2>/dev/null || true
cp -r ~/lazio-bot-backup/reports_pdf/* ./reports_pdf/ 2>/dev/null || true
```

### Step 7: Configura .env

Verifica che il file `.env` sia corretto:

```bash
nano .env
```

Controlla che contenga almeno:
```ini
TELEGRAM_BOT_TOKEN=il_tuo_token_qui
SERVER_NAME=raspberry-casa
LOG_LEVEL=INFO
TZ=Europe/Rome
```

### Step 8: Avvia con Docker

```bash
cd ~/lazio-health-bot

# Scarica l'immagine Docker
docker compose pull

# Avvia il bot
docker compose up -d

# Verifica che sia in esecuzione
docker compose ps
docker compose logs -f
```

Dovresti vedere:
```
INFO - Inizializzazione bot su server: raspberry-casa
INFO - Token Telegram caricato correttamente
INFO - Sistema multi-processo avviato
```

### Step 9: Testa il Bot

1. Apri Telegram
2. Cerca il tuo bot
3. Invia `/start`
4. Verifica che risponda con il menu principale

### Step 10: Verifica Salvataggio PDF

```bash
# Invia un comando al bot per scaricare un PDF
# Poi verifica che sia nella directory corretta:

ls -lh ~/lazio-health-bot/prenotazioni_pdf/
ls -lh ~/lazio-health-bot/reports_pdf/

# Se vedi i PDF qui, tutto funziona! ✅
```

---

## 🧹 Pulizia Post-Migrazione

### Rimuovi Vecchia Installazione Systemd

Dopo aver verificato che Docker funziona correttamente:

```bash
# Rimuovi la vecchia directory (ATTENZIONE: verifica prima di eliminare!)
cd ~
# Assicurati di aver fatto il backup prima!
rm -rf ~/LazioHealthMonitorBot

# Oppure rinominala per sicurezza
mv ~/LazioHealthMonitorBot ~/LazioHealthMonitorBot.old
```

### Cerca e Rimuovi PDF Sparsi

Se systemd ha salvato PDF in posti strani:

```bash
# Trova tutti i PDF del bot
sudo find / -name "*booking*.pdf" -o -name "*prenotazione*.pdf" 2>/dev/null

# Valuta se eliminarli (dopo averli copiati se necessario)
# sudo rm /path/to/stray/pdfs/*
```

---

## 🔧 Gestione Docker vs Systemd

### Comandi a Confronto

| Operazione | Systemd | Docker Compose |
|------------|---------|----------------|
| **Avvia bot** | `sudo systemctl start lazio-health-bot` | `docker compose up -d` |
| **Ferma bot** | `sudo systemctl stop lazio-health-bot` | `docker compose down` |
| **Riavvia bot** | `sudo systemctl restart lazio-health-bot` | `docker compose restart` |
| **Stato bot** | `sudo systemctl status lazio-health-bot` | `docker compose ps` |
| **Visualizza log** | `sudo journalctl -u lazio-health-bot -f` | `docker compose logs -f` |
| **Abilita autostart** | `sudo systemctl enable lazio-health-bot` | `restart: unless-stopped` (già nel compose) |
| **Disabilita autostart** | `sudo systemctl disable lazio-health-bot` | Rimuovi `restart: unless-stopped` |

---

## 📊 Verifica Migrazione Riuscita

### Checklist

- [ ] Il bot risponde su Telegram
- [ ] I log vengono scritti in `~/lazio-health-bot/logs/`
- [ ] Le prescrizioni monitorate sono presenti
- [ ] I PDF delle prenotazioni finiscono in `~/lazio-health-bot/prenotazioni_pdf/`
- [ ] I PDF dei referti finiscono in `~/lazio-health-bot/reports_pdf/`
- [ ] Il container si riavvia automaticamente dopo un reboot
- [ ] Il servizio systemd vecchio è fermo e disabilitato

### Test Completo

```bash
# 1. Verifica container running
docker compose ps
# Deve mostrare: Up

# 2. Verifica log recenti
docker compose logs --tail 20
# Nessun errore critico

# 3. Verifica directory
ls -la ~/lazio-health-bot/
# Deve mostrare: logs/, data/, reports_pdf/, prenotazioni_pdf/

# 4. Verifica autostart
docker inspect lazio-health-bot | grep -i restart
# Deve mostrare: "RestartPolicy": {"Name": "unless-stopped"}

# 5. Test riavvio sistema (opzionale)
sudo reboot
# Dopo il riavvio:
docker compose ps
# Il container deve essere automaticamente in esecuzione
```

---

## 🆘 Risoluzione Problemi Post-Migrazione

### Bot Non Si Avvia

**Problema**: Container si ferma subito

```bash
# Controlla log per errori
docker compose logs --tail 50

# Errore comune: Token mancante
# Soluzione: Verifica .env
cat .env | grep TELEGRAM_BOT_TOKEN
```

### PDF Ancora in Posti Sbagliati

**Problema**: I PDF non finiscono nelle directory mappate

```bash
# Verifica volumi montati
docker inspect lazio-health-bot | grep -A 20 Mounts

# Deve mostrare:
# "Source": "/home/user/lazio-health-bot/prenotazioni_pdf"
# "Destination": "/app/prenotazioni_pdf"
```

### Dati Persi

**Problema**: Prescrizioni o configurazioni non ci sono

```bash
# Ripristina dal backup
cp ~/lazio-bot-backup/input_prescriptions.json ~/lazio-health-bot/
cp ~/lazio-bot-backup/authorized_users.json ~/lazio-health-bot/

# Riavvia
docker compose restart
```

### Servizio Systemd Ancora Attivo

**Problema**: Entrambi systemd e Docker sono attivi

```bash
# Ferma definitivamente systemd
sudo systemctl stop lazio-health-bot
sudo systemctl disable lazio-health-bot
sudo systemctl mask lazio-health-bot

# Verifica
sudo systemctl status lazio-health-bot
# Deve mostrare: Loaded: masked
```

---

## 🔄 Rollback a Systemd (Se Necessario)

Se Docker non funziona e vuoi tornare a systemd:

```bash
# 1. Ferma Docker
docker compose down

# 2. Ripristina directory originale
mv ~/LazioHealthMonitorBot.old ~/LazioHealthMonitorBot
cd ~/LazioHealthMonitorBot

# 3. Ripristina configurazione
cp ~/lazio-bot-backup/.env .
cp ~/lazio-bot-backup/authorized_users.json .
cp ~/lazio-bot-backup/input_prescriptions.json .

# 4. Riavvia systemd (correggi prima il WorkingDirectory!)
sudo nano /etc/systemd/system/lazio-health-bot.service
# Aggiungi: WorkingDirectory=/home/pi/LazioHealthMonitorBot

sudo systemctl daemon-reload
sudo systemctl start lazio-health-bot
sudo systemctl enable lazio-health-bot
```

---

## 📈 Vantaggi Ottenuti

Dopo la migrazione a Docker:

✅ **Nessun problema con path relativi**: Working directory sempre `/app`
✅ **Aggiornamenti semplici**: Un comando invece di git pull + pip install
✅ **Isolamento**: Nessun conflitto con Python di sistema
✅ **Backup semplificato**: Tutto in una directory
✅ **Portabilità**: Funziona su qualsiasi sistema con Docker
✅ **Logs gestiti**: Rotazione automatica senza configurazione
✅ **Riproducibilità**: Stessa configurazione ovunque

---

## 📞 Supporto

Problemi durante la migrazione?

1. Controlla i log: `docker compose logs --tail 100`
2. Verifica la configurazione: `cat .env`
3. Consulta la [guida Docker completa](Installazione-Docker.md)
4. Apri una [Issue su GitHub](https://github.com/LucaTomei/LazioHealthMonitorBot/issues)

---

**Autore**: Luca Tomei
**Versione Guida**: 1.0
**Ultimo Aggiornamento**: Dicembre 2024

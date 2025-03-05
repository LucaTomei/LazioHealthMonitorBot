# Lazio Health Monitor Bot

Con questo bot telegram verrai notificato e terrai traccia delle disponibilità di appuntamenti con il SSN nella regione Lazio.

# Guida all'installazione del servizio di monitoraggio prenotazioni mediche

Questa guida ti aiuterà a configurare il servizio di monitoraggio delle prenotazioni mediche sul tuo Raspberry Pi, che controlla periodicamente la disponibilità e ti notifica su Telegram quando ci sono cambiamenti.

## Prerequisiti

- Raspberry Pi con Raspbian/Raspberry Pi OS installato
- Connessione a Internet
- Un bot Telegram (dovrai crearne uno)

## Passaggio 1: Creare un bot Telegram

1. Apri Telegram e cerca "@BotFather"
2. Invia il comando `/newbot`
3. Segui le istruzioni per creare un bot
4. Salva il token API fornito da BotFather
5. Avvia una chat con il tuo nuovo bot
6. Per ottenere il tuo ID chat, cerca "@userinfobot" su Telegram e invia un messaggio qualsiasi

## Passaggio 2: Preparare il Raspberry Pi

1. Aggiorna il sistema:
   ```
   sudo apt-get update
   sudo apt-get upgrade
   ```

2. Installa le dipendenze necessarie:
   ```
   sudo apt-get install python3-pip
   pip3 install requests
   ```

## Passaggio 3: Configurare il servizio

1. Crea una directory per il servizio:
   ```
   mkdir -p /home/pi/recup-monitor
   cd /home/pi/recup-monitor
   ```

2. Crea il file Python principale:
   ```
   nano recup_monitor.py
   ```
   
3. Copia e incolla il codice dal file `recup_monitor.py` fornito

4. Modifica le seguenti variabili nel file:
   - `TELEGRAM_TOKEN`: inserisci il token del tuo bot Telegram

5. Salva il file (Ctrl+O, quindi Invio, poi Ctrl+X)

6. Crea il file di input:
   ```
   nano input_prescriptions.json
   ```

7. Incolla il contenuto del file di esempio e modifica i dati con le tue prescrizioni:
   ```json
   [
      {
      "fiscal_code": "RSSMRA80A01H501Z",
      "nre": "1200A5555555555",
      "telegram_chat_id": "123456789",
      "config": {
            "only_new_dates": false,
            "notify_removed": true,
            "min_changes_to_notify": 1,
            "time_threshold_minutes": 30,
            "show_all_current": false
         }
      }
   ]
   ```

   ### Parametri di configurazione

   #### Parametri principali
   | Parametro | Tipo | Descrizione |
   |-----------|------|-------------|
   | `fiscal_code` | String | Codice fiscale del paziente |
   | `nre` | String | Numero di Ricetta Elettronica da monitorare |
   | `telegram_chat_id` | String | ID della chat Telegram a cui inviare le notifiche per questa prescrizione specifica |

   ### Opzioni di configurazione (`config`)
   | Opzione | Tipo | Default | Descrizione |
   |---------|------|---------|-------------|
   | `only_new_dates` | Boolean | `true` | Se `true`, riceverai notifiche solo per nuove disponibilità (non per rimozioni o cambiamenti di prezzo) |
   | `notify_removed` | Boolean | `false` | Se `true`, riceverai notifiche quando le disponibilità vengono rimosse |
   | `min_changes_to_notify` | Number | `2` | Numero minimo di cambiamenti prima di inviare una notifica |
   | `time_threshold_minutes` | Number | `60` | Minuti entro cui considerare due appuntamenti come lo stesso spostato di orario |
   | `show_all_current` | Boolean | `true` | Se `true`, il messaggio includerà tutte le disponibilità attuali, non solo le nuove |



8. Salva il file (Ctrl+O, quindi Invio, poi Ctrl+X)

## Passaggio 4: Configurare il servizio systemd

1. Crea il file di servizio systemd:
   ```
   sudo nano /etc/systemd/system/recup-monitor.service
   ```

2. Copia e incolla il contenuto di:
    ```
    [Unit]
    Description=Recup Monitor Service
    After=network.target

    [Service]
    Type=simple
    User=pi
    WorkingDirectory=/home/pi/home-automation-api/recup/
    ExecStart=/usr/bin/python3 /home/pi/home-automation-api/recup/recup_monitor.py
    Restart=on-failure
    RestartSec=10
    StandardOutput=syslog
    StandardError=syslog
    SyslogIdentifier=recup-monitor

    [Install]
    WantedBy=multi-user.target
    ```

3. Salva il file (Ctrl+O, quindi Invio, poi Ctrl+X)

4. Abilita e avvia il servizio:
   ```
   sudo systemctl daemon-reload
   sudo systemctl enable recup-monitor.service
   sudo systemctl start recup-monitor.service
   ```

5. Verifica che il servizio sia in esecuzione:
   ```
   sudo systemctl status recup-monitor.service
   ```

## Passaggio 5: Monitoraggio e manutenzione

### Per controllare i log del servizio:
```
sudo journalctl -u recup-monitor.service
```

### Per vedere solo gli ultimi log:
```
sudo journalctl -u recup-monitor.service -f
```

### Per riavviare il servizio dopo modifiche:
```
sudo systemctl restart recup-monitor.service
```

### Per aggiornare le prescrizioni da monitorare:
Modifica il file `input_prescriptions.json` con le nuove prescrizioni che desideri monitorare.

## Funzionamento del servizio

Il servizio eseguirà le seguenti operazioni ogni 5 minuti:

1. Leggerà il file `input_prescriptions.json` per ottenere i codici fiscali e i numeri NRE da monitorare
2. Per ogni prescrizione, verificherà le disponibilità mediche
3. Confronterà le disponibilità attuali con quelle precedenti
4. Se ci sono cambiamenti (nuove disponibilità, disponibilità rimosse o prezzi cambiati), invierà una notifica su Telegram
5. Salverà i dati attuali per il confronto successivo

## Risoluzione dei problemi

### Il servizio non si avvia
Controlla i log di sistema:
```
sudo journalctl -u recup-monitor.service
```

### Non ricevo notifiche Telegram
1. Verifica di aver inserito correttamente il token del bot e l'ID chat
2. Assicurati di aver avviato una chat con il tuo bot
3. Controlla i log per eventuali errori nelle chiamate API Telegram
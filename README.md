# Lazio Health Monitor Bot

Un bot Telegram avanzato che monitora automaticamente le disponibilità del Servizio Sanitario Nazionale nella Regione Lazio, invia notifiche quando sono disponibili nuovi appuntamenti e permette la prenotazione diretta degli appuntamenti.

![Banner](https://img.shields.io/badge/Regione-Lazio-green)
![Python](https://img.shields.io/badge/Python-3.7+-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 📋 Caratteristiche

- 🔍 **Monitoraggio automatico**: Controlla le disponibilità ogni 5 minuti
- 🔔 **Notifiche intelligenti**: Ricevi avvisi personalizzati quando ci sono nuovi appuntamenti
- 📅 **Filtro date**: Configura notifiche solo per appuntamenti entro un periodo specificato
- 🏥 **Prenotazione diretta**: Prenota appuntamenti direttamente dal bot
- 🤖 **Prenotazione automatica**: Prenota automaticamente il primo slot disponibile
- 📝 **Gestione prenotazioni**: Visualizza e disdici le tue prenotazioni attive
- 📄 **PDF delle prenotazioni**: Ricevi automaticamente la conferma della prenotazione in PDF
- 👥 **Sistema multi-utente**: Gestione di utenti autorizzati
- 📱 **Interfaccia intuitiva**: Tastiera personalizzata per una facile interazione
- 📊 **Dettagli completi**: Visualizza ospedali, date, orari e costi
- 🔐 **Accesso sicuro**: Solo gli utenti autorizzati possono utilizzare il bot
- ⚡ **Architettura multi-processo**: Interazione reattiva anche durante le scansioni

## 🚀 Guida all'installazione

### Prerequisiti

- Python 3.7+
- `python-telegram-bot` (v20.0+)
- `requests`
- `urllib3`

```bash
# Installa le dipendenze
pip install python-telegram-bot requests urllib3
```

### Passaggio 1: Creare un bot Telegram

1. Apri Telegram e cerca "@BotFather"
2. Invia il comando `/newbot`
3. Segui le istruzioni per creare un bot
4. Salva il token API fornito da BotFather
5. Avvia una chat con il tuo nuovo bot
6. Per ottenere il tuo ID chat, cerca "@userinfobot" su Telegram e invia un messaggio qualsiasi

### Configurazione

1. Clona il repository:
```bash
git clone https://github.com/yourusername/lazio-health-monitor.git
cd lazio-health-monitor
```

2. Configura il bot:
   - Modifica il token Telegram nel file `config.py`
   - Personalizza altre impostazioni se necessario

3. Esegui il bot:
```bash
# Versione standard (monitoraggio e bot nello stesso processo)
python recup_monitor.py

# Versione multi-processo (più reattiva)
python recup_monitor_multiprocess.py
```

## 🎮 Utilizzo

### Comandi principali

- `/start` - Avvia il bot e mostra il menu principale
- `/cancel` - Annulla l'operazione corrente

### Menu del bot

- **➕ Aggiungi Prescrizione** - Aggiungi una nuova prescrizione da monitorare
- **➖ Rimuovi Prescrizione** - Smetti di monitorare una prescrizione
- **📋 Lista Prescrizioni** - Visualizza le prescrizioni in monitoraggio
- **🔄 Verifica Disponibilità** - Controlla immediatamente le disponibilità
- **🔔 Gestisci Notifiche** - Attiva/disattiva notifiche per una prescrizione
- **⏱ Imposta Filtro Date** - Filtra le notifiche entro un periodo di mesi
- **🏥 Prenota** - Prenota un appuntamento per una prescrizione
- **🤖 Prenota Automaticamente** - Prenota automaticamente il primo slot disponibile
- **📝 Le mie Prenotazioni** - Visualizza e gestisci le prenotazioni attive
- **ℹ️ Informazioni** - Mostra informazioni sul bot
- **🔑 Autorizza Utente** - (Solo admin) Autorizza nuovi utenti ad utilizzare il bot

### Come aggiungere una prescrizione

1. Seleziona "➕ Aggiungi Prescrizione"
2. Inserisci il codice fiscale del paziente
3. Inserisci il codice NRE (Numero Ricetta Elettronica)
4. Conferma l'aggiunta

Il bot verificherà la validità della prescrizione e inizierà a monitorarla automaticamente.

### Come prenotare un appuntamento

1. Seleziona "🏥 Prenota"
2. Scegli la prescrizione da prenotare
3. Inserisci il tuo numero di telefono e email
4. Visualizza le disponibilità e seleziona quella preferita
5. Conferma la prenotazione
6. Ricevi il PDF di conferma direttamente in chat

### Come prenotare automaticamente

1. Seleziona "🤖 Prenota Automaticamente"
2. Scegli la prescrizione da prenotare
3. Inserisci il tuo numero di telefono e email
4. Il sistema prenoterà automaticamente il primo slot disponibile
5. Ricevi il PDF di conferma direttamente in chat

### Come gestire le prenotazioni

1. Seleziona "📝 Le mie Prenotazioni"
2. Visualizza l'elenco delle prenotazioni attive
3. Per disdire una prenotazione, seleziona "❌ Disdici una prenotazione"
4. Scegli quale prenotazione disdire
5. Conferma la disdetta

## 🔒 Gestione degli utenti

Il bot implementa un sistema di autorizzazione:

- Il primo utente che interagisce con il bot diventa automaticamente l'amministratore
- Solo l'amministratore può autorizzare nuovi utenti
- Gli utenti non autorizzati non possono utilizzare il bot

Per autorizzare un nuovo utente:
1. L'amministratore seleziona "🔑 Autorizza Utente"
2. Inserisce l'ID Telegram dell'utente da autorizzare
3. L'utente autorizzato può ora utilizzare il bot

## 📁 Struttura del progetto

### File principali
- `config.py` - Configurazioni e costanti globali
- `recup_monitor.py` - Versione standard del bot
- `recup_monitor_multiprocess.py` - Versione multi-processo per maggiore reattività

### Directory e moduli
- `/modules/` - Directory dei moduli
  - `api_client.py` - Funzioni per l'interazione con l'API RecUP
  - `booking_client.py` - Funzioni per la prenotazione appuntamenti
  - `bot_handlers.py` - Gestori per i comandi del bot Telegram
  - `data_utils.py` - Utilità per la gestione dei dati
  - `monitoring.py` - Funzioni per il monitoraggio delle prescrizioni
  - `prescription_processor.py` - Elaborazione delle prescrizioni

### File di dati
- `input_prescriptions.json` - Salva le prescrizioni monitorate
- `previous_data.json` - Memorizza i dati delle disponibilità precedenti
- `authorized_users.json` - Elenco degli utenti autorizzati
- `recup_monitor.log` - File di log con rotazione automatica

## ⚙️ Configurazione delle prescrizioni

### Parametri di base
| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `fiscal_code` | String | Codice fiscale del paziente |
| `nre` | String | Numero di Ricetta Elettronica da monitorare |
| `telegram_chat_id` | Number | ID della chat Telegram per le notifiche |
| `notifications_enabled` | Boolean | Se abilitare le notifiche |
| `description` | String | Descrizione della prescrizione (autopopolata) |
| `patient_info` | Object | Informazioni sul paziente (autopopolate) |
| `bookings` | Array | Prenotazioni associate (se presenti) |

### Opzioni di configurazione (`config`)
| Opzione | Tipo | Default | Descrizione |
|---------|------|---------|-------------|
| `only_new_dates` | Boolean | `true` | Notifiche solo per nuove disponibilità |
| `notify_removed` | Boolean | `false` | Notifiche per disponibilità rimosse |
| `min_changes_to_notify` | Number | `1` | Numero minimo di cambiamenti per la notifica |
| `time_threshold_minutes` | Number | `60` | Considera due appuntamenti variati dello stesso orario |
| `show_all_current` | Boolean | `true` | Mostra tutte le disponibilità nel messaggio |
| `months_limit` | Number/null | `null` | Filtra appuntamenti entro X mesi (null = nessun limite) |

## 🎛️ Architettura

### Standard vs Multi-processo

Il bot può essere eseguito in due modalità:

1. **Standard** (`recup_monitor.py`):
   - Bot e monitoraggio funzionano nello stesso processo
   - Utilizzo di memoria più efficiente
   - Potenziali rallentamenti durante la scansione

2. **Multi-processo** (`recup_monitor_multiprocess.py`):
   - Bot e monitoraggio in processi separati
   - Interazione reattiva anche durante le scansioni
   - Utilizzo di memoria leggermente maggiore
   - Isolamento degli errori tra i processi

### Flusso di dati

1. **Monitoraggio**:
   - Caricamento delle prescrizioni da `input_prescriptions.json`
   - Interrogazione dell'API RecUP per ogni prescrizione
   - Confronto con i dati precedenti in `previous_data.json`
   - Invio di notifiche in caso di cambiamenti significativi

2. **Prenotazione**:
   - Autenticazione con l'API RecUP
   - Verifica della disponibilità per la prescrizione
   - Pre-prenotazione dello slot selezionato
   - Conferma della prenotazione con i dati di contatto
   - Download e invio del PDF di conferma

## 🔧 Risoluzione dei problemi

- **Errore di autorizzazione**: Assicurati che il tuo ID Telegram sia nella lista degli utenti autorizzati.
- **Nessun appuntamento trovato**: Verifica che il codice fiscale e l'NRE siano corretti.
- **Bot non risponde**: Prova la versione multi-processo per una maggiore reattività.
- **Prenotazione fallita**: Verifica che i dati di contatto siano corretti e che lo slot sia ancora disponibile.
- **Errori nei file**: Controlla i log in `recup_monitor.log` per dettagli.
- **"Non disponibile" nei messaggi**: Potrebbe esserci un problema con la descrizione della prescrizione. Rimuovila e aggiungila di nuovo.

## 🔄 Aggiornamenti futuri

- Supporto per più regioni oltre al Lazio
- Interfaccia web per la gestione
- Supporto per prescrizioni multiple in un'unica prenotazione
- Ricerca intelligente di appuntamenti basata su preferenze di località e orario

## 📜 Licenza

Questo progetto è rilasciato sotto licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.

## 📞 Contatti

Per domande, suggerimenti o segnalazioni di bug, apri un issue su GitHub o contattami direttamente.

---

⚠️ **Disclaimer**: Questo bot utilizza un'API non ufficiale del sistema RecUP della Regione Lazio. È stato creato solo per scopi personali e educativi. L'utilizzo del bot è a tuo rischio e pericolo. L'autore non è responsabile per eventuali problemi derivanti dall'utilizzo di questo software.


## 📜 Licenza

Questo progetto è rilasciato sotto licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.
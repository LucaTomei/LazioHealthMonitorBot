# Lazio Health Monitor Bot

Un bot Telegram che monitora automaticamente le disponibilità del Servizio Sanitario Nazionale nella Regione Lazio e invia notifiche quando sono disponibili nuovi appuntamenti.

![Banner](https://img.shields.io/badge/Regione-Lazio-green)
![Python](https://img.shields.io/badge/Python-3.7+-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## 📋 Caratteristiche

- 🔍 **Monitoraggio automatico**: Controlla le disponibilità ogni 5 minuti
- 🔔 **Notifiche istantanee**: Ricevi avvisi quando ci sono nuovi appuntamenti
- 👥 **Sistema multi-utente**: Gestione di utenti autorizzati
- 📱 **Interfaccia intuitiva**: Tastiera personalizzata per una facile interazione
- 📊 **Dettagli completi**: Visualizza ospedali, date, orari e costi
- 🔐 **Accesso sicuro**: Solo gli utenti autorizzati possono utilizzare il bot

# Guida all'installazione del servizio di monitoraggio prenotazioni mediche

Questa guida ti aiuterà a configurare il servizio di monitoraggio delle prenotazioni mediche sul tuo Raspberry Pi, che controlla periodicamente la disponibilità e ti notifica su Telegram quando ci sono cambiamenti.

## Prerequisiti

- Python 3.7+
- `python-telegram-bot` (v20.0+)
- `requests`

```bash
# Installa le dipendenze
pip install python-telegram-bot requests
```

## Passaggio 1: Creare un bot Telegram

1. Apri Telegram e cerca "@BotFather"
2. Invia il comando `/newbot`
3. Segui le istruzioni per creare un bot
4. Salva il token API fornito da BotFather
5. Avvia una chat con il tuo nuovo bot
6. Per ottenere il tuo ID chat, cerca "@userinfobot" su Telegram e invia un messaggio qualsiasi

## Configurazione

1. Clona il repository:
```bash
git clone https://github.com/yourusername/ssn-telegram-bot.git
cd ssn-telegram-bot
```

2. Configura il bot:
   - Modifica il token Telegram nel file `recup_monitor.py`
   - Personalizza altre impostazioni se necessario

3. Esegui il bot:
```bash
python recup_monitor.py
```

## 🚀 Utilizzo

### Comandi principali

- `/start` - Avvia il bot e mostra il menu principale
- `/cancel` - Annulla l'operazione corrente

### Menu del bot

- **➕ Aggiungi Prescrizione** - Aggiungi una nuova prescrizione da monitorare
- **➖ Rimuovi Prescrizione** - Smetti di monitorare una prescrizione
- **📋 Lista Prescrizioni** - Visualizza le prescrizioni in monitoraggio
- **🔄 Verifica Disponibilità** - Controlla immediatamente le disponibilità
- **ℹ️ Informazioni** - Mostra informazioni sul bot
- **🔑 Autorizza Utente** - (Solo admin) Autorizza nuovi utenti ad utilizzare il bot

### Come aggiungere una prescrizione

1. Seleziona "➕ Aggiungi Prescrizione"
2. Inserisci il codice fiscale del paziente
3. Inserisci il codice NRE (Numero Ricetta Elettronica)
4. Conferma l'aggiunta

Il bot verificherà la validità della prescrizione e inizierà a monitorarla automaticamente.

## 🔒 Gestione degli utenti

Il bot implementa un sistema di autorizzazione:

- Il primo utente che interagisce con il bot diventa automaticamente l'amministratore
- Solo l'amministratore può autorizzare nuovi utenti
- Gli utenti non autorizzati non possono utilizzare il bot

Per autorizzare un nuovo utente:
1. L'amministratore seleziona "🔑 Autorizza Utente"
2. Inserisce l'ID Telegram dell'utente da autorizzare
3. L'utente autorizzato può ora utilizzare il bot

## 📁 Struttura dei file

- `recup_monitor.py` - File principale del bot
- `input_prescriptions.json` - Salva le prescrizioni monitorate
- `previous_data.json` - Memorizza i dati delle disponibilità precedenti
- `authorized_users.json` - Elenco degli utenti autorizzati

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

## 📝 Note tecniche

Il bot utilizza l'API non ufficiale del sistema RecUP della Regione Lazio. Effettua le seguenti operazioni:

1. Ottiene un token di accesso
2. Verifica i dati del paziente e della prescrizione
3. Ottiene le disponibilità per la prescrizione
4. Confronta con le disponibilità precedenti
5. Invia notifiche quando ci sono nuovi appuntamenti

## 🔧 Risoluzione dei problemi

- **Errore di autorizzazione**: Assicurati che il tuo ID Telegram sia nella lista degli utenti autorizzati.
- **Nessun appuntamento trovato**: Verifica che il codice fiscale e l'NRE siano corretti.
- **Bot non risponde**: Riavvia il bot e controlla i log per eventuali errori.
- **Errori nei file**: Usa il comando `/debug` per verificare lo stato dei file di sistema.

## 📜 Licenza

Questo progetto è rilasciato sotto licenza MIT. Vedi il file [LICENSE](LICENSE) per i dettagli.

## 📞 Contatti

Per domande, suggerimenti o segnalazioni di bug, apri un issue su GitHub o contattami direttamente.

---

⚠️ **Disclaimer**: Questo bot utilizza un'API non ufficiale del sistema RecUP della Regione Lazio. È stato creato solo per scopi personali e educativi. L'utilizzo del bot è a tuo rischio e pericolo. L'autore non è responsabile per eventuali problemi derivanti dall'utilizzo di questo software.

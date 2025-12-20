# 🔄 GitHub Actions Workflows

Questo repository utilizza GitHub Actions per CI/CD automatizzato.

## 📋 Workflows Disponibili

### 1. CI Validation (`ci-validation.yml`)

**Trigger**: Ogni push su qualsiasi branch e PR verso main/develop

**Scopo**: Validazione automatica del codice prima del merge

#### Job eseguiti:

##### ✅ Python Validation
- Verifica sintassi Python di tutti i file `.py`
- Testa che tutti gli import funzionino correttamente
- Controlla che non ci siano path hardcoded nel codice
- Installa e testa tutte le dipendenze

##### 🐳 Docker Validation
- Valida il `Dockerfile` con build test
- Testa che l'immagine Docker si avvii correttamente
- Valida la sintassi di entrambi i file docker-compose
- Verifica che tutti i volumi necessari siano mappati
- Controlla che prenotazioni_pdf e reports_pdf siano presenti

##### 📁 Structure Validation
- Verifica che tutti i file necessari esistano
- Controlla che `.env.example` contenga tutte le variabili
- Valida che `.gitignore` escluda file sensibili
- Verifica la presenza di tutta la documentazione

##### 🔒 Security Checks
- Scansiona il codice per secrets hardcoded
- Verifica che il container non giri come root
- Controlla che l'healthcheck sia presente nel Dockerfile
- Valida che non ci siano API key nel codice

#### Risultati:
- ✅ **Success**: Tutti i check passano - codice pronto per merge
- ❌ **Failure**: Uno o più check falliti - review richiesta

---

### 2. Docker Publish (`docker-publish.yml`)

**Trigger**:
- Push su branch `main` o `develop`
- Push di tag `v*` (es. v1.0.0, v2.1.3)
- Pull request verso `main`
- Manuale via workflow_dispatch

**Scopo**: Build e pubblicazione dell'immagine Docker su GitHub Container Registry (GHCR)

#### Caratteristiche:

##### Multi-architettura
Build per:
- `linux/amd64` (PC normali, server, cloud)
- `linux/arm64` (Raspberry Pi 3B+, 4, 5, server ARM)

##### Tagging Strategy
Le immagini vengono taggate automaticamente:
- `main` → `latest`
- `develop` → `develop`
- `v1.2.3` → `1.2.3`, `1.2`, `1`, `latest`
- PR → `pr-123`
- Commit → `sha-abc123`

##### Caching
Utilizza GitHub Actions cache per build più veloci:
- Cache delle layer Docker
- Riutilizzo tra build successive
- Riduzione tempo di build fino all'80%

##### Attestation
Genera attestazioni di provenienza per sicurezza della supply chain

#### Pull dell'immagine:

```bash
# Ultima versione stabile
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest

# Versione specifica
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:1.2.3

# Branch develop (testing)
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:develop

# Commit specifico
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:sha-abc123
```

---

## 🎯 Workflow per Developer

### Sviluppo di una nuova feature

```bash
# 1. Crea branch
git checkout -b feature/nuova-funzione

# 2. Sviluppa e committa
git add .
git commit -m "feat: aggiunge nuova funzione"

# 3. Push
git push -u origin feature/nuova-funzione
# ✅ Trigger: CI Validation automatico

# 4. Verifica che CI passi su GitHub Actions

# 5. Apri PR verso develop
# ✅ Trigger: CI Validation + Docker build test

# 6. Dopo merge su develop
# ✅ Trigger: Docker build e push con tag "develop"

# 7. Merge su main (release)
# ✅ Trigger: Docker build e push con tag "latest"
```

### Creare una release

```bash
# 1. Assicurati di essere su main aggiornato
git checkout main
git pull origin main

# 2. Crea tag semantico
git tag -a v1.2.3 -m "Release v1.2.3: descrizione release"

# 3. Push del tag
git push origin v1.2.3
# ✅ Trigger: Docker build con tag v1.2.3, 1.2, 1, latest

# 4. Crea release su GitHub (opzionale)
gh release create v1.2.3 --title "v1.2.3" --notes "Release notes..."
```

---

## 🔍 Monitoraggio dei Workflows

### Visualizzare lo stato

1. Vai su: https://github.com/LucaTomei/LazioHealthMonitorBot/actions
2. Seleziona il workflow desiderato
3. Visualizza i dettagli di ogni job

### Badges per README

Aggiungi badge allo stato delle pipeline:

```markdown
![CI Validation](https://github.com/LucaTomei/LazioHealthMonitorBot/actions/workflows/ci-validation.yml/badge.svg)
![Docker Publish](https://github.com/LucaTomei/LazioHealthMonitorBot/actions/workflows/docker-publish.yml/badge.svg)
```

### Notifiche

GitHub invia notifiche automatiche quando:
- Un workflow fallisce sul tuo branch
- Tutti i check passano su una PR
- Una nuova immagine Docker viene pubblicata

---

## 🐛 Troubleshooting

### CI Validation fallisce

**Python Validation Error**:
```bash
# Testa localmente
python -m py_compile recup_monitor.py
python -c "import config"

# Controlla dipendenze
pip install -r requirements.txt
```

**Docker Validation Error**:
```bash
# Valida docker-compose localmente
docker compose -f docker-compose.ghcr.yml config

# Testa build
docker build -t test:local .
```

**Structure Validation Error**:
```bash
# Verifica file mancanti
ls -la

# Controlla .env.example
cat .env.example
```

### Docker Publish fallisce

**Permission Error**:
- Verifica che il repository abbia permessi per pubblicare su GHCR
- Settings → Actions → General → Workflow permissions → Read and write

**Build Error**:
- Controlla i log dettagliati su GitHub Actions
- Testa il build localmente: `docker build .`

**Multi-arch Build Error**:
- Alcune dipendenze potrebbero non supportare ARM
- Verifica requirements.txt per pacchetti problematici

---

## ⚙️ Configurazione Avanzata

### Secrets e Variabili

Il workflow usa questi secrets/variabili automatici:
- `GITHUB_TOKEN`: Fornito automaticamente da GitHub
- `github.actor`: Username che ha triggerato il workflow
- `github.sha`: SHA del commit corrente

### Modificare i Workflow

Per modificare i workflow:

```bash
# Edita il file workflow
nano .github/workflows/ci-validation.yml

# Committa
git add .github/workflows/
git commit -m "ci: aggiorna workflow CI"
git push

# Il workflow modificato sarà attivo dal prossimo push
```

### Test manuale di un workflow

Usa `workflow_dispatch` per eseguire manualmente:

1. Vai su Actions → Workflow desiderato
2. Click su "Run workflow"
3. Seleziona branch
4. Click "Run workflow"

---

## 📊 Metriche

### Tempo di esecuzione tipico

| Workflow | Durata Media | Costo |
|----------|--------------|-------|
| CI Validation | 3-5 minuti | Gratis (Actions) |
| Docker Publish (no cache) | 8-12 minuti | Gratis (Actions) |
| Docker Publish (con cache) | 2-4 minuti | Gratis (Actions) |

### Limiti GitHub Actions

- **Free tier**: 2000 minuti/mese per repository privati
- **Public repos**: Minuti illimitati
- **Storage**: 500MB per artifacts e cache

---

## 🔗 Link Utili

- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Docker Build Push Action](https://github.com/docker/build-push-action)
- [GitHub Container Registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
- [Repository Actions](https://github.com/LucaTomei/LazioHealthMonitorBot/actions)

---

## 📝 Changelog Workflows

### v1.0 (Corrente)
- ✅ CI Validation completa con 4 job
- ✅ Docker Publish multi-architettura
- ✅ Caching ottimizzato
- ✅ Attestation di sicurezza
- ✅ Tagging semantico automatico

---

**Autore**: Luca Tomei
**Ultimo Aggiornamento**: Dicembre 2024

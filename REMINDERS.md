# Guida Release - Come Pubblicare Nuove Versioni

## 📋 Overview

Quando pushì su `main`, GitHub Actions automaticamente:
1. ✅ Builda l'immagine Docker
2. ✅ Pusha su GHCR con tag `latest`
3. ❌ ERRORE attuale: attestation fallisce

Per fare **release versionate** (v1.0.0, v1.1.0, etc.):


## 🏷️ STEP 2: Creare una Release

### Metodo A: Git Tag (Raccomandato)

```bash
# 1. Assicurati di essere su main aggiornato
git checkout main
git pull origin main

# 2. Crea e pusha il tag
git tag -a v1.0.0 -m "Release v1.0.0 - Initial stable release"
git push origin v1.0.0
```

**Cosa succede automaticamente**:
- GitHub Actions builda l'immagine
- Crea questi tag:
  - `ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0`
  - `ghcr.io/lucatomei/laziohealthmonitorbot:1.0`
  - `ghcr.io/lucatomei/laziohealthmonitorbot:1`
  - `ghcr.io/lucatomei/laziohealthmonitorbot:latest`

### Metodo B: GitHub Web UI

1. Vai su: https://github.com/LucaTomei/LazioHealthMonitorBot/releases
2. Click "Create a new release"
3. Click "Choose a tag" → Scrivi `v1.0.0` → "Create new tag"
4. **Release title**: `v1.0.0 - Initial Release`
5. **Description**: Descrivi le novità
6. Click "Publish release"

---

## 🔄 Workflow Completo Release

### 1. Sviluppo
```bash
# Lavora sul codice
git checkout -b feature/nuova-funzionalita
# ... modifica codice ...
git commit -m "feat: aggiungi nuova funzionalità"
git push origin feature/nuova-funzionalita
```

### 2. Test su develop (opzionale)
```bash
# Merge su develop per test
git checkout develop
git merge feature/nuova-funzionalita
git push origin develop

# GitHub Actions builda: ghcr.io/.../bot:develop
# Testa su server staging
```

### 3. Release su main
```bash
# Merge su main
git checkout main
git pull origin main
git merge develop
git push origin main

# GitHub Actions builda: ghcr.io/.../bot:latest
```

### 4. Tag versione
```bash
# Crea release
git tag -a v1.1.0 -m "Release v1.1.0"
git push origin v1.1.0

# GitHub Actions builda: ghcr.io/.../bot:v1.1.0
```

---

## 🎯 Release Notes Template

Quando crei una release su GitHub, usa questo template:

```markdown
## 🎉 v1.1.0 - Nome Release

### ✨ Nuove Feature
- Aggiunto supporto multi-regione
- Implementato sistema di backup automatico

### 🐛 Bug Fixes
- Risolto errore fcntl su Windows
- Fixato crash durante l'avvio

### 📝 Modifiche
- Aggiornata documentazione
- Migliorata performance del 30%

### ⚠️ Breaking Changes
- Nuovo formato per `config.json` (vedi migration guide)

### 📦 Docker Images
```bash
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:v1.1.0
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

### 🔧 Migration Guide
Se aggiorni da v1.0.x:
1. Backup dei dati
2. Update config.json (esempio sotto)
3. Restart container

### 📚 Documentazione
- [Guida Installazione](USER_INSTALL_GUIDE.md)
- [Changelog Completo](CHANGELOG.md)
```

---

## 📊 Verifica Release

Dopo aver creato la release:

### 1. Verifica GitHub Actions
```
https://github.com/LucaTomei/LazioHealthMonitorBot/actions
```
Deve essere tutto ✅ verde

### 2. Verifica Immagini GHCR
```
https://github.com/LucaTomei?tab=packages
```
Dovresti vedere i nuovi tag

### 3. Test Pull
```bash
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

### 4. Test Funzionale
```bash
docker run --env-file .env ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0
```

---

## 🔖 Gestione Tags

### Lista tutti i tag
```bash
git tag -l
```

### Elimina tag locale
```bash
git tag -d v1.0.0
```

### Elimina tag remoto
```bash
git push origin :refs/tags/v1.0.0
```

### Rinomina tag
```bash
# Non si può rinominare direttamente
# Elimina vecchio e crea nuovo
git tag -d v1.0.0
git push origin :refs/tags/v1.0.0
git tag -a v1.0.1 -m "..."
git push origin v1.0.1
```

---

## 📈 Best Practices

### 1. CHANGELOG.md
Mantieni un file CHANGELOG.md:

```markdown
# Changelog

## [1.1.0] - 2024-12-09
### Added
- Multi-region support
- Automatic backup

### Fixed
- Windows fcntl error

## [1.0.0] - 2024-12-01
### Added
- Initial release
```

### 2. Pre-release Testing
```bash
# Crea pre-release tag
git tag -a v1.1.0-beta.1 -m "Beta release for testing"
git push origin v1.1.0-beta.1
```

### 3. Hotfix Process
```bash
# Per bug critici in production
git checkout v1.0.0
git checkout -b hotfix/critical-bug
# fix bug
git commit -m "hotfix: critical bug"
git tag -a v1.0.1 -m "Hotfix: critical bug"
git push origin v1.0.1
git checkout main
git merge hotfix/critical-bug
```

---

## 🚨 Rollback

Se una release ha problemi:

### 1. Gli utenti possono usare versione precedente
```bash
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0
```

### 2. Puoi ri-taggare latest
```bash
# Pusha di nuovo v1.0.0 come latest
docker pull ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0
docker tag ghcr.io/lucatomei/laziohealthmonitorbot:v1.0.0 ghcr.io/lucatomei/laziohealthmonitorbot:latest
docker push ghcr.io/lucatomei/laziohealthmonitorbot:latest
```

---

## 🎯 Quick Commands

```bash
# Release patch (bug fix)
git tag -a v1.0.1 -m "Fix: descrizione" && git push origin v1.0.1

# Release minor (feature)
git tag -a v1.1.0 -m "Feature: descrizione" && git push origin v1.1.0

# Release major (breaking)
git tag -a v2.0.0 -m "Breaking: descrizione" && git push origin v2.0.0

# Lista release
git tag -l "v*"

# Verifica ultima release
git describe --tags --abbrev=0
```

---

## ✅ Checklist Release

Prima di ogni release:

- [ ] Codice testato localmente
- [ ] Tests passati (se esistono)
- [ ] CHANGELOG.md aggiornato
- [ ] Documentazione aggiornata
- [ ] Version bump in file (se necessario)
- [ ] Commit su main
- [ ] Tag creato
- [ ] GitHub Actions completato ✅
- [ ] Immagine verificata su GHCR
- [ ] Release notes pubblicate su GitHub
- [ ] Testato pull e avvio container
- [ ] Comunicato agli utenti (se necessario)

---

## 🔗 Link Utili

- **Actions**: https://github.com/LucaTomei/LazioHealthMonitorBot/actions
- **Releases**: https://github.com/LucaTomei/LazioHealthMonitorBot/releases
- **Packages**: https://github.com/LucaTomei?tab=packages
- **Semantic Versioning**: https://semver.org/

---

**Tempo per release**: 5 minuti  
**Difficoltà**: Facile  
**Frequenza consigliata**: Ogni volta che aggiungi feature o fix bug importanti

Buon releasing! 🚀
# 📋 INSTRUCTIONS — Hiflow Monitor

## Ce que fait ce script
- Vérifie les missions Hiflow toutes les 60 secondes
- Surveille Paris / Île-de-France en continu
- Surveille Toulouse jusqu'au 22 mars 2026
- T'envoie une notification Telegram dès qu'une nouvelle mission apparaît

---

## 🚀 Déploiement sur Railway (gratuit, tourne 24h/24)

### Étape 1 — Créer un compte Railway
1. Va sur https://railway.app
2. Clique "Start a New Project"
3. Connecte-toi avec GitHub (crée un compte GitHub si besoin)

### Étape 2 — Créer un dépôt GitHub
1. Va sur https://github.com/new
2. Nom du dépôt : `hiflow-monitor`
3. Laisse tout par défaut, clique "Create repository"
4. Sur la page suivante, clique "uploading an existing file"
5. Glisse-dépose le fichier `hiflow_monitor.py`
6. Glisse-dépose aussi le fichier `requirements.txt`
7. Clique "Commit changes"

### Étape 3 — Déployer sur Railway
1. Sur Railway, clique "New Project" → "Deploy from GitHub repo"
2. Sélectionne ton dépôt `hiflow-monitor`
3. Railway détecte automatiquement Python
4. Dans les settings du projet, va dans "Variables" et ajoute :
   - Aucune variable nécessaire, tout est dans le script

### Étape 4 — Vérifier que ça tourne
1. Va dans l'onglet "Logs" sur Railway
2. Tu devrais voir : "🚀 Hiflow Monitor démarré !"
3. Et recevoir un message Telegram de confirmation !

---

## ⚠️ Important — Renouveler le cookie

Le cookie de session expire après quelques jours/semaines.
Quand les notifications s'arrêtent, il faut :
1. Retourner sur partenaire.expedicar.com
2. Répéter l'inspection réseau (F12 → Network → Fetch/XHR)
3. Copier le nouveau cookie
4. Mettre à jour la ligne COOKIE= dans le script

---

## 🔧 Modifier les filtres

Pour changer la zone ou la date Toulouse, modifie ces lignes dans hiflow_monitor.py :

```python
TOULOUSE_DATE_LIMIT = "2026-03-22"  # changer la date
CHECK_INTERVAL = 60  # changer l'intervalle (en secondes)
```

---

## 🔐 Sécurité

Après avoir tout configuré, pense à régénérer le token Telegram :
1. Ouvre @BotFather sur Telegram
2. Envoie /mybots → sélectionne ton bot → API Token → Revoke
3. Remplace le token dans le script

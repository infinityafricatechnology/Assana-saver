# Déployer Infinity Planning sur Coolify

Ce guide met en ligne une instance de test d'Infinity Planning sur un serveur géré par Coolify (v4). Toute l'application est construite à partir de ce dépôt avec `docker-compose.coolify.yml`. Coolify génère les mots de passe et le certificat HTTPS.

## Ce qui tourne

| Service                                              | Rôle                                                                                 |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `proxy`                                              | Point d'entrée unique (Caddy, port 80), seul service exposé au public                |
| `web`, `admin`, `space`                              | Application, administration de l'instance (`/god-mode`), pages publiques (`/spaces`) |
| `live`                                               | Édition collaborative des pages (`/live`)                                            |
| `api`, `worker`, `beat-worker`                       | API Django et tâches de fond                                                         |
| `migrator`                                           | Applique les migrations de la base à chaque déploiement, puis s'arrête               |
| `mcp`                                                | Connecteur Claude (`/mcp`)                                                           |
| `plane-db`, `plane-redis`, `plane-mq`, `plane-minio` | PostgreSQL, Valkey, RabbitMQ, stockage des fichiers                                  |

Le proxy de Coolify (Traefik) reçoit le HTTPS et transmet tout au service `proxy`. Celui-ci répartit ensuite selon le chemin : `/api`, `/auth` et `/static` vont vers l'API, `/god-mode` vers l'administration, `/spaces` vers les pages publiques, `/live` vers l'édition collaborative, `/mcp` vers le connecteur Claude, `/uploads` vers le stockage, et tout le reste vers l'application.

## Prérequis

- Un serveur avec Coolify v4 installé. Prévoir au moins 4 vCPU, 8 Go de RAM et 40 Go de disque : la première construction compile trois applications web.
- Un nom de domaine, par exemple `planning.infinity-africa.com`, avec un enregistrement DNS `A` vers l'adresse IP du serveur.
- L'accès au dépôt GitHub `3lkfadel/Assana-saver` depuis Coolify. Comme le dépôt est privé, on passe par l'application GitHub de Coolify.

## 1. Créer l'application

1. Dans Coolify : **Projects**, puis le projet voulu, puis **+ New**, puis **Private Repository (with GitHub App)**. Choisissez `3lkfadel/Assana-saver`.
2. **Branch** : `main`.
3. **Build Pack** : `Docker Compose`.
4. **Docker Compose Location** : `/docker-compose.coolify.yml`.
5. Validez. Coolify lit le fichier et affiche la liste des services.

## 2. Domaine

Dans la liste des services, ouvrez **proxy**, puis **Domains**, et saisissez `https://planning.infinity-africa.com`. Les autres services ne reçoivent pas de domaine.

Coolify demande le certificat Let's Encrypt au premier déploiement ; le DNS doit donc déjà pointer vers le serveur. Pour un essai sans nom de domaine, gardez l'adresse `sslip.io` que Coolify propose.

## 3. Variables d'environnement

Coolify crée seul les identifiants et secrets (`SERVICE_USER_*`, `SERVICE_PASSWORD_*`) et l'URL publique (`SERVICE_URL_PROXY`). Il ne faut pas les modifier après le premier déploiement : la base et le stockage les ont déjà enregistrés.

Variables réglables dans **Environment Variables** :

| Variable                  | Valeur par défaut       | Quand la changer                                                                                                                                     |
| ------------------------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `INFINITY_WORKSPACE_SLUG` | `infinity-africa-group` | Si l'organisation est créée avec un autre identifiant (voir étape 5)                                                                                 |
| `MINIO_ENDPOINT_SSL`      | `1`                     | Mettre `0` si l'instance est servie en `http://` (adresse `sslip.io` sans HTTPS)                                                                     |
| `FILE_SIZE_LIMIT`         | `5242880` (5 Mo)        | Pour accepter des pièces jointes plus lourdes, en octets                                                                                             |
| `WEB_STATIC_RATE_LIMIT`   | `5000`                  | Fichiers statiques par minute et par adresse IP publique. Un premier chargement en demande environ 250, et tout un bureau partage souvent la même IP |
| `GUNICORN_WORKERS`        | `2`                     | Pour plus de requêtes simultanées sur l'API, si la RAM le permet                                                                                     |
| `API_KEY_RATE_LIMIT`      | `60/minute`             | Limite des jetons d'API (les jetons Claude ont leur propre limite)                                                                                   |

## 4. Déployer

Cliquez sur **Deploy**. Le premier déploiement prend 15 à 25 minutes, car toutes les images sont construites. Les suivants réutilisent le cache.

Le service `migrator` applique les migrations puis s'arrête : c'est normal. L'API attend la fin des migrations avant de démarrer.

Pour vérifier que tout tourne :

- `https://planning.infinity-africa.com/api/instances/` renvoie du JSON ;
- la page de connexion s'affiche sur `https://planning.infinity-africa.com`.

## 5. Première configuration

1. **Administrateur de l'instance** : ouvrez `https://planning.infinity-africa.com/god-mode/` et créez le compte administrateur. Le mot de passe doit être long et difficile à deviner (au moins 12 caractères, sans nom ni année) : un mot de passe qui ne satisfait que les critères affichés peut être refusé.
2. **E-mails** (codes de connexion, notifications) : _Email_, avec le serveur SMTP du groupe.
3. **Connexion** : dans _Authentication_, activez les **codes uniques par e-mail** (_Unique codes_) et désactivez l'**inscription libre** (_Allow anyone to sign up_). Seules les personnes pré-inscrites depuis la page « Personnes » pourront alors entrer.
4. **Assistant IA** : _AI → Claude (Anthropic)_, avec la clé d'API Anthropic.
5. **Organisation** : depuis `https://planning.infinity-africa.com`, créez votre compte puis l'organisation. Donnez-lui l'identifiant `infinity-africa-group`, ou reportez l'identifiant choisi dans `INFINITY_WORKSPACE_SLUG` puis redéployez.
6. **Référentiel du Groupe** : _Réglages de l'organisation → Référentiel du Groupe → Charger le référentiel du Groupe_.
7. **Personnes** : _Réglages de l'organisation → Personnes_. Ajoutez les testeurs un par un, ou importez une liste, avec leur rôle, leurs profils de pilotage et leurs projets. Chacun reçoit un e-mail et se connecte avec un code.
8. **Claude** : chacun relie Claude depuis _Réglages du profil → Connecter Claude_. L'adresse du connecteur est `https://planning.infinity-africa.com/mcp`.
9. **Espace de pilotage** : dans les réglages de chaque projet, choisissez l'**entité porteuse**. Le projet devient piloté : ses tâches se créent complètes et tout report d'échéance demande un motif. Donnez ensuite les **profils de pilotage** (PDG, Cabinet, directeur de pôle, responsable d'entité) depuis la page « Personnes ». L'espace apparaît dans la barre latérale des personnes concernées.

Les automatismes de l'espace de pilotage tournent dans `beat-worker` et `worker`. Ces deux services doivent rester démarrés, et le SMTP doit être configuré (étape 2). Les heures sont celles d'Abidjan :

- tous les jours à 7 h, les alertes d'échéance, de retard, de risque et de File PDG ;
- toutes les 10 minutes, l'alerte de levée de blocage ;
- le lundi à 8 h, la relance automatique des fiches dormantes ou incohérentes ;
- le vendredi à 12 h, l'instantané hebdomadaire et le projet de rapport, annoncé au Cabinet et au PDG.

## Mettre à jour

Chaque fusion dans `main` peut être déployée avec **Redeploy**. Pour un déploiement automatique à chaque push, activez **Auto Deploy** dans la configuration de l'application. Les migrations s'appliquent seules.

## Sauvegardes

Les données sont dans des volumes Docker : `pgdata` (base) et `uploads` (fichiers). Pour une sauvegarde ponctuelle de la base, depuis le serveur en SSH (le nom exact du conteneur `plane-db` apparaît dans `docker ps`) :

```bash
docker exec <conteneur-plane-db> sh -c 'pg_dump -U "$POSTGRES_USER" plane' > sauvegarde-$(date +%F).sql
```

Avant de passer en production, mettez en place une sauvegarde planifiée de ces deux volumes.

## Dépannage

| Symptôme                                           | Cause probable et correction                                                                  |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| « Unable to fetch instance details » à l'ouverture | L'API démarre encore ou attend les migrations : voir les journaux de `migrator` puis de `api` |
| Pièces jointes et images qui ne s'affichent pas    | `MINIO_ENDPOINT_SSL` ne correspond pas au protocole du domaine (`1` en HTTPS, `0` en HTTP)    |
| Claude répond « 401 »                              | Jeton absent ou révoqué : en générer un nouveau dans _Connecter Claude_                       |
| Claude ne trouve pas les projets                   | `INFINITY_WORKSPACE_SLUG` ne correspond pas à l'identifiant de l'organisation                 |
| Erreurs 429 (« Too Many Requests ») au chargement  | Plusieurs personnes derrière la même IP : augmenter `WEB_STATIC_RATE_LIMIT`                   |
| La construction échoue faute de mémoire            | Augmenter la RAM du serveur, ou ajouter de l'espace d'échange (swap) avant de relancer        |

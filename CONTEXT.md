# Infinity Planning

Outil interne de gestion du travail d'Infinity Africa Group. Il reproduit les fonctionnalités d'Asana et repose sur un fork de Plane (dépôt `Assana-saver`). L'interface utilise le vocabulaire d'Asana, en français et en anglais.

## Langage

### Travail

**Tâche** :
L'unité de travail : un nom, une description, un responsable au plus, des dates, des collaborateurs. Elle appartient à zéro, un ou plusieurs projets ; elle n'a pas de projet d'origine.
_Éviter_ : work item, issue, ticket

**Identifiant de tâche** :
Le code court et permanent d'une tâche, unique dans l'espace de travail (`T-1234`), indépendant de ses projets.
_Éviter_ : clé projet, `PROJ-123`

**Sous-tâche** :
Une tâche rattachée à une tâche parente, sans limite de profondeur. Elle n'appartient à aucun projet tant qu'on ne l'y ajoute pas explicitement.
_Éviter_ : sub-issue, sub-work item

**Jalon** :
Une tâche d'un type particulier qui marque une étape datée d'un projet. Elle a une seule date et s'affiche en losange sur la timeline.
_Éviter_ : milestone, livrable

**Dépendance** :
Le lien entre deux tâches selon lequel l'une (bloquée) ne peut pas avancer avant que l'autre (bloquante) soit terminée.
_Éviter_ : relation, blocker

**Champ personnalisé** :
Une propriété ajoutée aux tâches d'un projet, d'un type donné (liste, liste multiple, texte, nombre, date, personne, référence). Il est défini une fois dans la bibliothèque de l'organisation et réutilisable dans plusieurs projets.
_Éviter_ : propriété, custom property, attribut

**Terminée** :
L'état binaire d'une tâche, coché ou non. L'avancement détaillé passe par le statut de pilotage, pas par cet état.
_Éviter_ : état, state, statut (pour désigner la complétion)

### Organisation

**Organisation** :
L'espace de travail unique du groupe, qui contient toutes les équipes, tous les projets et toutes les personnes.
_Éviter_ : workspace, espace de travail (en interface), groupe

**Équipe** :
Un ensemble de personnes qui possède des projets au sein de l'organisation. Chaque filiale du groupe est représentée par au moins une équipe.
_Éviter_ : filiale (en interface), teamspace, département

**Confidentialité d'équipe** :
Le niveau de visibilité d'une équipe pour le reste de l'organisation : publique (ses projets publics sont visibles de tous), sur demande (on demande à la rejoindre, valeur par défaut) ou privée (invisible pour les non-membres).
_Éviter_ : cloisonnement, accès

**Projet** :
Un ensemble de tâches rangées en sections et consultées à travers des vues (liste, tableau, timeline, calendrier).
_Éviter_ : board

**Section** :
Un groupe ordonné de tâches propre à un projet. Il s'affiche comme en-tête en vue liste et comme colonne en vue tableau.
_Éviter_ : colonne, état, statut, groupe

**Appartenance** :
Le lien entre une tâche et un projet. Une tâche a une appartenance par projet qui la contient, et chaque appartenance place la tâche dans une section de ce projet.
_Éviter_ : multi-homing (en interface), lien, copie

### Pilotage

**Espace de pilotage** :
Les écrans de lecture réservés au PDG, au Cabinet de la Présidence et aux responsables, qui suivent le travail de tout le Groupe par pôle et par entité.
_Éviter_ : dashboard, tableau de bord (pour désigner l'ensemble)

**Groupe** :
Infinity Africa Group en tant que structure : ses pôles et ses entités. Il est décrit par le référentiel du Groupe ; l'organisation, elle, est l'espace de travail qui contient les projets.
_Éviter_ : organisation (pour désigner la structure juridique)

**Pôle** :
Un regroupement d'entités du Groupe (Finance & Capital Markets, Immobilier, Fonctions Groupe…).
_Éviter_ : branche, division, département

**Entité** :
Une filiale ou une fonction support du Groupe, rattachée à un seul pôle.
_Éviter_ : équipe, société, département

**Entité porteuse** :
L'entité qui porte un projet. Chaque projet en a une seule.
_Éviter_ : propriétaire, entité responsable

**Catégorie** :
La nature d'une tâche dans l'espace de pilotage (Agréments, Gouvernance, Partenariats, Développement…), tenue par le Cabinet.
_Éviter_ : type, étiquette

**Fiche de pilotage** :
Les informations d'une tâche que lit l'espace de pilotage : entité, catégorie, superviseur, approbateur, statut, avancement, cause d'attente, risque, clôture et point de situation. Elle est incomplète tant qu'un champ obligatoire manque.
_Éviter_ : formulaire, métadonnées

**Statut** :
L'étape d'une tâche dans l'espace de pilotage, parmi six valeurs fixes : À démarrer, En cours, En validation, En attente, Terminé, Annulé. Il ne dépend pas de la section où se trouve la tâche.
_Éviter_ : état, section, colonne

**Superviseur** :
La personne qui suit l'exécution d'une tâche sans en être responsable.
_Éviter_ : manager, collaborateur

**Approbateur** :
La personne qui valide une tâche ; c'est le PDG lorsque la tâche requiert sa décision.
_Éviter_ : valideur, reviewer

**Priorité** :
L'importance d'une tâche, parmi trois valeurs : Urgent, Important, Normal. Elle range la File PDG et les retards ; le Cabinet ou le PDG peut la requalifier pour la File PDG sans changer celle déclarée par l'entité.
_Éviter_ : high, medium, low, aucune priorité

**Point de situation** :
Un texte libre et daté qui résume où en est une tâche.
_Éviter_ : commentaire, note, statut

**Profil de pilotage** :
Ce qu'une personne voit dans l'espace de pilotage : tout le Groupe (PDG, Cabinet de la Présidence), un pôle (directeur de pôle) ou une entité (responsable d'entité). Une personne peut en avoir plusieurs.
_Éviter_ : rôle (réservé aux droits dans l'organisation et les projets)

### Personnes

**Membre** :
Une personne du groupe, pré-inscrite dans l'organisation par un administrateur avec son adresse `@infinity-africa.com`. Il n'existe pas d'invités extérieurs.
_Éviter_ : utilisateur, invité, guest

**Pré-inscription** :
L'ajout d'une personne par un administrateur, depuis la page « Personnes ». Son compte, son rôle, ses profils de pilotage et ses projets existent avant sa première connexion.
_Éviter_ : invitation, inscription

**Départ** :
La fermeture des accès d'une personne qui quitte le Groupe. Ses tâches ouvertes sont confiées à quelqu'un d'autre, et son historique est conservé.
_Éviter_ : suppression, désactivation (en interface)

**Responsable** :
La seule personne chargée d'une tâche. Une tâche a zéro ou un responsable, jamais plusieurs.
_Éviter_ : assigné(s), assignee, owner

**Collaborateur** :
Une personne qui suit une tâche et reçoit ses notifications, sans en être responsable.
_Éviter_ : abonné, follower, subscriber, watcher

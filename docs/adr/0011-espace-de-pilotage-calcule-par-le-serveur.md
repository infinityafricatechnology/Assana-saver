# Un espace de pilotage calculé par le serveur, en lecture seule

L'espace de pilotage (cahier des charges §6) lit les tâches des projets pilotés. Il n'a pas de données propres. Le serveur calcule les signaux, les règles RG-01 à RG-14, à la date du jour du fuseau Africa/Abidjan. L'écran ne fait que filtrer et afficher.

- **Périmètre.** Le serveur restreint lui-même ce que chacun lit (§10). Le PDG, le Cabinet et les administrateurs de l'espace de travail voient tout le Groupe. Un directeur de pôle voit son pôle, un responsable d'entité son entité. Une personne qui a plusieurs profils voit la réunion de leurs périmètres. Les points d'accès sont tous en lecture seule. Les quatre actions permises (décision du PDG, requalification, relance, rapport) passent par leurs propres points d'accès, qui contrôlent les droits.
- **Temps réel.** L'écran interroge toutes les quatre secondes une empreinte de version, une requête légère. Il ne recharge le portefeuille que si elle a changé. Une modification apparaît donc en moins de cinq secondes (§12), sans renvoyer les 5 000 tâches à chaque fois.
- **Exports.** Le serveur produit le PDF COMEX avec reportlab (police Vera fournie avec la bibliothèque). Il produit aussi l'Excel de la liste filtrée, dont l'écran envoie les identifiants dans l'ordre affiché. Le PDF est un document français marqué « Confidentiel », comme les e-mails d'alerte. Le rapport hebdomadaire du vendredi (§9.3) partira de ce même PDF.

Mesure : 5 000 tâches se chargent en 0,7 s une fois le serveur chaud, et l'empreinte en moins de 0,1 s.

## Options écartées

- **Calculer les signaux dans le navigateur** : le PDF, le rapport hebdomadaire et les alertes auraient leur propre version des règles, et les cas de contrôle du §5 se testeraient en deux endroits.
- **Imprimer la page pour obtenir le PDF** : le rapport du vendredi midi doit être produit sans navigateur ouvert, puis archivé.
- **Pousser les changements par WebSocket** : une infrastructure de plus à exploiter, alors qu'une empreinte interrogée toutes les quatre secondes tient l'exigence.

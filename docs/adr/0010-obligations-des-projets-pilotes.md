# Obligations réservées aux projets pilotés

Le cahier des charges (§4, §9.4) impose deux règles : une tâche ne s'enregistre pas tant qu'un champ obligatoire manque, et un report de deadline sans commentaire est refusé. Nous les appliquons aux seuls projets pilotés, c'est-à-dire portés par une entité du référentiel. Les autres projets gardent la création libre de Plane.

Dans un projet piloté :

- **Création.** Le serveur refuse une tâche sans responsable, échéance, catégorie, superviseur ou approbateur, quel que soit le chemin : application, brouillon, API v1, création en lot ou Claude. Le refus porte le code `steering_required` et la liste des champs manquants. L'entité est facultative, puisque par défaut c'est celle du projet. La fenêtre de création affiche un bloc « Pilotage », et l'ajout rapide ouvre cette fenêtre.
- **Modification.** Le responsable, l'échéance, la catégorie, le superviseur et l'approbateur ne peuvent plus être vidés.
- **Report.** Repousser l'échéance demande un `deadline_comment` (code `deadline_comment_required`). L'application demande le motif où que la date change : liste, tableau, chronologie ou fiche. Le report et son motif entrent dans l'historique (`deadline_postponed`).

## Options écartées

- **Appliquer les règles à tous les projets** : les espaces de travail courants (prospection, notes, projets personnels) deviendraient lourds sans servir le pilotage du Groupe.
- **Contrôler seulement dans l'interface** : l'API v1, les imports et Claude passeraient outre, alors que l'espace de pilotage repose sur des fiches complètes.
- **Refuser les reports depuis la chronologie** : le glisser-déposer y est l'usage courant. L'application demande donc le motif et le serveur l'accepte aussi sur ce chemin.

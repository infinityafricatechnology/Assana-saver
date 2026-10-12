# Trois priorités : Urgent, Important, Normal

Le cahier des charges (§4, §5, §8.2) classe les retards et la File PDG selon trois priorités : Urgent, Important et Normal. Plane en propose cinq (urgent, high, medium, low, none). Nous gardons les valeurs internes de Plane et en réduisons le jeu : `urgent` reste Urgent, `high` devient Important, `medium` devient Normal.

- Une migration (`0129_infinity_three_priorities`) a reporté les tâches `low` et `none` sur Normal. Normal devient la priorité par défaut.
- Un signal avant enregistrement reporte toute autre valeur sur Normal, quel que soit le chemin : application, API v1, serveur MCP ou import.
- L'interface et le serveur MCP ne proposent plus que les trois valeurs.

## Options écartées

- **Garder cinq priorités et les regrouper dans l'espace de pilotage** : la File PDG et les retards prioritaires (RG-12) se liraient avec un vocabulaire différent de celui des espaces des entités.
- **Ajouter un champ « Priorité de pilotage »** : deux priorités par tâche à tenir à jour, pour une seule information.

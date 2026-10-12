# Charte Infinity Planning

Relevée le 2026-10-07 sur [infinity-africa.com](https://infinity-africa.com/) (feuille de style `css/adventria.webflow.shared.f8d9c9c64.css` et page d'accueil).

## Logo

- `source/logo-infinity-africa-group.png` : logo du groupe (812 × 307), blanc et gris sur fond transparent, prévu pour fond sombre.
- `source/symbole-infinity-512.png`, `-192.png`, `apple-touch-icon-180.png` : le symbole seul, blanc sur fond quasi noir.

### Fichiers dérivés pour Infinity Planning

- `logo/symbole-clair.svg`, `logo/symbole-sombre.svg` : le symbole redessiné en vectoriel (boîte 347 × 182), anthracite ou blanc givré.
- `logo/logo-clair.svg`, `logo/logo-sombre.svg` : symbole et « Infinity Planning » en Inter.
- `icons/` : favicons et icônes d'application (symbole blanc sur carré anthracite), générés par `tools/brand/render_icons.py`. La commande `python3 tools/brand/render_icons.py --apps --font <Inter.ttf>` régénère les icônes et l'image de partage des trois applications.
- Logo des e-mails : `apps/api/plane/static/emails/`, généré par `tools/brand/render_email_logo.py`.
- Dans l'interface, `PlaneLockup` et `PlaneLogo` (`packages/blocks/src/icons/brand/`) dessinent le logo Infinity Planning. Ils gardent leur nom Plane pour faciliter la reprise des correctifs de sécurité (ADR 0003).
- Sur les fonds anthracite de l'interface web (barre de navigation, panneau des écrans de connexion), le logo blanc du groupe est affiché : `apps/web/app/assets/logos/infinity-africa-group-white.png`, la source rognée de ses marges transparentes.

## Couleurs

| Rôle sur le site       | Nom (variable CSS du site)         | Valeur                 |
| ---------------------- | ---------------------------------- | ---------------------- |
| Texte et fonds sombres | `--prussian-blue` / `--slate-gray` | `#2A2D2F`              |
| Fond clair             | `--frost-white`                    | `#F5F9FA`              |
| Gris secondaire        | `--cadet-blue-gray`                | `#AEBDC1`              |
| Bordures               | `--light-gray`                     | `#E2E2E2`              |
| Teinte douce           | `--light-periwinkle`               | `#D5D6F4`              |
| Accent (icônes, liens) | —                                  | `#DE2748` et `#DC143C` |
| Noir profond           | —                                  | `#161616`              |

## Typographie

- Titres : **Inter** (libre, déjà utilisée par Plane).
- Texte courant sur le site : **Century Gothic** (police commerciale Monotype ; l'intégrer en webfont demande une licence).

## Décisions pour Infinity Planning

- **Logo** : le symbole Infinity du groupe suivi de « Planning » (ou « Infinity Planning ») en Inter, redessiné en SVG en deux versions, pour fond clair et pour fond sombre. À faire valider par la communication du groupe si elle encadre l'usage du symbole.
- **Couleur principale** : anthracite `#2A2D2F` pour les boutons, la navigation et la sélection. Le carmin `#DC143C` est réservé aux moments de marque (logo, page de connexion, célébration de tâche terminée). Les alertes (retard, erreur, suppression) utilisent un rouge distinct du carmin.
- **Police** : Jost (libre, géométrique, proche de Century Gothic) pour les titres, le message d'accueil, le fil d'Ariane et l'écran de connexion ; Inter pour le texte courant et les listes denses. Century Gothic n'est pas intégrée.
- **Formes** : coins de 8 px pour les contrôles et de 12 px pour les cartes ; ombres teintées anthracite.
- **Navigation** : cadre anthracite ; l'élément actif est une pastille blanc givré (`ip-nav-on`, générée par `tools/brand/build-nav-theme.mjs`).
- **États vides** : le symbole Infinity aux couleurs d'illustration du thème (pervenche douce `#D5D6F4`, gris cadet) remplace les illustrations de Plane.
- **Thème** : clair par défaut, avec un thème sombre « Infinity » au choix.

# Conception — Plooum CamPreview

## Besoin

Garder, pour une caméra, une image d'aperçu prise à intervalle régulier, en ignorant les images inutiles (noires, caméra tournée), avec une mise à jour forcée, et sans jamais finir par tout ignorer (jour / nuit / infrarouge). L'image sert à la projection d'une caméra dans la carte floorplan de HA-Plooum-Cards, puis à une future carte d'aperçu en direct quand le flux est indisponible.

## Choix

- **Intégration côté serveur** plutôt que dans la carte : la capture tourne même sans tableau de bord ouvert, l'aperçu est partagé par tous les navigateurs et survit au redémarrage. La carte floorplan faisait déjà ce filtrage dans le navigateur (`projection_picture: live`) ; l'intégration reprend la même mesure (contours 64 × 36, corrélation, seuil 0,5) pour que les deux s'accordent.
- **Une entrée de configuration, une sous-entrée par caméra** (depuis la 0.2.0) : « Ajouter une caméra », réglages par caméra (reconfiguration de la sous-entrée), suppression qui efface l'image et l'état gardés. La 0.1.0 avait une entrée par caméra : la migration (version 1 → 2) fait de la caméra une sous-entrée qui garde l'identifiant de l'entrée, donc ses fichiers, ses entités et son appareil (rattachés à la sous-entrée).
- **Entité `image`** : servie par HA (`/api/image_proxy/…` avec jeton), son état est l'heure de l'image : une carte ne recharge l'image que quand l'état change.
- **Pillow seul**, pas de numpy : la signature fait 4 608 nombres, le calcul en Python pur prend quelques millisecondes, dans l'exécuteur.
- **Filtre pur** (`analysis.py`, `decision.py`) sans dépendance à HA : testable en isolation (`tests/test_filter.py`, scènes synthétiques jour / crépuscule / infrarouge / rotation / ronde PTZ).

## Garde-fous contre « tout ignorer »

Voir le README (section *Never ignoring everything*) et la docstring de `decision.py`. En résumé : une référence par mode (couleur / IR), références qui suivent les changements lents, adoption d'une nouvelle vue stable, acceptation de dernier recours après `max_age_hours`, mise à jour forcée. Les images noires ne déclenchent jamais d'adoption : la nuit sans IR garde l'image de jour.

## Persistance

`.storage/plooum_campreview.<subentry_id>` (références, état du filtre) et `.storage/plooum_campreview/<subentry_id>.img` (la dernière bonne image). Supprimés avec la caméra ou l'entrée.

## Carte floorplan (HA-Plooum-Cards)

Option de caméra `preview_entity` : la caméra projette l'aperçu (prioritaire sur `projection_picture`) et son écran affiche « Camera moved? Re-align it » quand l'attribut `moved` est vrai.

Limite connue : quand l'intégration adopte une nouvelle vue (`rebased` / `stale`), la projection suit la nouvelle image alors que la caméra n'est plus alignée dans la carte. L'événement `plooum_campreview_view_changed` permet de prévenir ; une piste serait que la carte compare `view_since` à la date de son alignement.

## Suite

- Carte d'aperçu de caméra : flux en direct, et l'image de l'aperçu (avec son âge) quand le flux est indisponible.
- Éventuellement : ramener une caméra PTZ sur un préréglage avant la capture.

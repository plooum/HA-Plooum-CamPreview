# Plooum CamPreview

*[English version](README.md)*

Une intégration Home Assistant qui garde un **aperçu régulier et filtré** d'une caméra : toutes les quelques minutes, elle prend une image et ne la garde que si elle est bonne. Une image noire, un écran uniforme « pas de signal », ou l'image d'une caméra qui a tourné (PTZ, un coup) est ignorée : l'aperçu garde la dernière bonne image.

L'aperçu est une entité `image` ordinaire, conservée au redémarrage. Les cartes peuvent s'en servir là où une image de caméra doit rester pertinente, par exemple la projection d'une caméra sur une façade ou une pièce dans la [carte floorplan](https://github.com/plooum/HA-Plooum-Cards/blob/main/docs/floorplan.md) (`preview_entity`), ou comme image de secours quand le flux de la caméra est indisponible.

## Installation

HACS → Intégrations → ⋮ → Dépôts personnalisés → `https://github.com/plooum/HA-Plooum-CamPreview` (catégorie *Intégration*), installer **Plooum CamPreview**, redémarrer Home Assistant. Puis **Paramètres → Appareils et services → Ajouter une intégration → Plooum CamPreview**, et choisir les caméras de départ.

## Plusieurs caméras

L'intégration s'installe une seule fois ; chaque caméra en est une partie, avec ses propres réglages :

- **Ajouter une caméra** sur la page de l'intégration en ajoute une, avec ses réglages ;
- la ⚙ d'une caméra change ses réglages ;
- ⋮ → **Supprimer** sur une caméra la retire, avec ses entités et l'image gardée.

Mise à jour depuis la 0.1.0 (une entrée d'intégration par caméra) : chaque entrée devient une entrée Plooum CamPreview qui contient sa caméra, avec les mêmes entités, réglages et image. On peut ajouter de nouvelles caméras à n'importe laquelle.

## Entités

Pour une caméra `camera.jardin` :

| Entité | Quoi |
| :--- | :--- |
| `image.jardin_preview` | L'aperçu : la dernière bonne image. Son état est l'heure de cette image. Attributs : `camera_entity`, `status`, `moved` (vrai tant que les images sont ignorées parce que la caméra a tourné), `last_reason`, `score` (ressemblance avec la vue habituelle, 0–1), `mode` (`color` ou `ir`), `brightness`, `contrast`, `rejections` (d'affilée), `last_attempt`, `view_since` (depuis quand la caméra montre sa vue actuelle), `moved_since`, `references`, `error`. |
| `sensor.jardin_preview_status` | Résultat de la dernière capture : `ok`, `black`, `uniform`, `moved`, `unavailable`, `error`, `waiting`. |
| `button.jardin_preview_force_update` | **Forcer la mise à jour** : prend l'image actuelle quoi qu'elle montre, et en fait la nouvelle vue habituelle de la caméra (après l'avoir tournée exprès). |

Action `plooum_campreview.update` (cible : n'importe laquelle de ces entités, un appareil ou une pièce) : capture une image tout de suite ; avec `force: true`, comme le bouton.

Événement `plooum_campreview_view_changed` (`camera_entity`, `reason` : `rebased`, `stale` ou `forced`) : la vue habituelle de la caméra a changé. Pratique pour être prévenu qu'une caméra a été tournée.

## Comment les images sont filtrées

Chaque image est réduite aux **contours** d'une petite copie en gris. Les contours changent à peine avec la lumière du jour ou dans une vue de nuit infrarouge grise, alors qu'une rotation de quelques degrés les déplace tous. Une image est comparée à la **vue habituelle** de la caméra :

- **noire** : ses parties les plus claires sont plus sombres que le *niveau de noir* → ignorée.
- **uniforme** : presque aucun contraste (écran gris ou bleu « pas de signal ») → ignorée.
- **déplacée** : ses contours ne ressemblent plus à la vue habituelle (*seuil de ressemblance*, 0,5 par défaut : une rotation d'environ 3 % de l'image) → ignorée.

### Ne jamais tout ignorer

Un filtre qui compare à une image fixe peut finir par rejeter toutes les images pour toujours (nuit, infrarouge, saisons, caméra tournée pour de bon). Garde-fous :

1. **Une vue habituelle par mode** : couleur (jour) et infrarouge (nuit) ont chacun leur référence. La première image infrarouge est comparée avec indulgence et devient la référence de nuit.
2. **Les références suivent les changements lents** : une image qui ressemble nettement devient la nouvelle référence de son mode (lumière, saisons, voiture garée).
3. **Une nouvelle vue stable est adoptée** : quand plusieurs images ignorées d'affilée (3 par défaut) se ressemblent sur au moins 10 minutes, la caméra pointe vraiment ailleurs : cette vue devient l'habituelle (`plooum_campreview_view_changed`, raison `rebased`). Une caméra PTZ en ronde, dont les images changent sans cesse, n'est pas adoptée.
4. **Dernier recours** : après 12 heures sans image acceptée alors que des images exploitables arrivent, la dernière est acceptée (`stale`).
5. **Forcer la mise à jour** (bouton ou action) prend toujours l'image.

Les images noires et uniformes ne comptent jamais pour 3 et 4 : une caméra sans infrarouge garde sa dernière image de jour pendant la nuit, ce qu'un aperçu doit montrer.

## Options

Réglés à l'ajout d'une caméra, modifiables ensuite par sa ⚙ (**Paramètres → Appareils et services → Plooum CamPreview**). Les caméras choisies à l'installation partent des valeurs par défaut :

| Option | Défaut | |
| :--- | :--- | :--- |
| Intervalle de capture | 300 s | Temps entre deux captures (au moins 30 s). |
| Niveau de noir | 25 | 0–255. Une image dont les parties les plus claires (98e centile de la luminance) sont plus sombres est noire. |
| Contraste minimum | 3 | Écart type de la luminance sous lequel une image est uniforme. |
| Seuil de ressemblance | 0,5 | 0–1. Plus bas tolère plus (caméra qui tremble), plus haut détecte des rotations plus petites. |
| Images semblables pour adopter une nouvelle vue | 3 | 0 : n'adopte jamais de nouvelle vue tout seul. |
| ...sur au moins | 10 min | |
| Accepter quand même après | 12 h | 0 : jamais. |

## Développement

Le filtre (`analysis.py`, `decision.py`) ne dépend pas de Home Assistant ; ses tests ne demandent que Pillow :

```bash
python -m unittest discover tests
```

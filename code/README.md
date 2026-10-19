# Codes R1, R2 et outils d'exploitation

Les fichiers des trois éditions sont copiés octet pour octet depuis les archives vérifiées. Les versions historiques sont séparées :

Dans les copies consultables, les trois fichiers `.gitattributes` d'origine portent le nom inerte `.gitattributes.archived`. Leur contenu reste identique ; cela empêche leurs anciennes règles Git de modifier les fins de ligne des autres fichiers. Les ZIP conservent les noms et octets d'origine, et `SOURCES.json` inventorie les noms publiés.

| Édition | Sources consultables | Fichiers | Archive SHA-256 |
| --- | --- | ---: | --- |
| R1 historique lié à Luna MAX, job 748259 | [r1-historical](r1-historical/README.md) | 90 | `cd769d474b6cb14c2fba11ab687f8825d35cb0b57a397d09aefab0ae743ffc18` |
| Harnais de comparaison dérivé | [r1-comparison](r1-comparison/README.md) | 94 | `9a68a83fde4acb6bd247d79e00490e7d36f0c4c59c6c881152101e4c499387eb` |
| R2 natif de la matrice quinze sujets | [r2-native](r2-native/README.md) | 127 | `b79e6fdc3e1e0dae5d9d240353510c504ffc1298265a6d425f248a8f2b5489d4` |

Le R1 historique est relié à la cohorte indiquée ; cette attribution ne prouve pas que tous les anciens résultats utilisaient la même archive. La dérivée de comparaison reste distincte. Les archives originales, les inventaires et le [guide exact de restauration](../reproducibility/reexecution-r1-r2-r2/LIRE-MOI.md) sont conservés. [SOURCES.json](SOURCES.json) donne les empreintes de toutes les copies consultables.

Le répertoire `operations/` rend également consultables 226 fichiers de scripts et de tests des producteurs, récepteurs, contrôles d'admission, audits, outils d'article et prototypes. Leurs versions et reçus complets sont conservés dans le [catalogue intégral](../reproducibility/README.md), avec les autres variantes historiques et leurs fichiers de données.

Les documents copiés gardent leurs anciennes références locales ; les liens actuels sont ceux de ce point d'entrée. Les références historiques sont à interpréter dans leur workspace restauré.

La campagne reste en pause. Les snapshots R2 gardent le problème de publication READY observé dans l'essai Astra. Le prototype de barrière séparé a été testé hors ligne et n'est pas intégré au runtime : le publier ne corrige pas rétroactivement les anciens jobs. Les anciens identifiants, réservations et délais ne doivent pas être rejoués.

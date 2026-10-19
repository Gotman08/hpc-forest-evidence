# Astra755862 — constat en lecture seule

Job FAILED1:0, pipeline incomplet. Aucun snapshot de pause du premier batch. Le reçu source reste technical_errors_found:true et invocation_unknown:true. Les deux réponses locales ont été livrées sans erreur CLI/infrastructure, pour30919 tokens exacts ; aucun hold. Les deux PID connus34384/66520 étaient encore présents à observation, sans claim de capacité globale.

L’archive originale a été reçue et vérifiée par SCP :9c52bda58c3f5a78d325261479cf9e9813eef5edbefbd4215f49a638f5244342,179031 octets,295 membres, aucun lien. Lecture virtuelle uniquement, sans extraction ni exécution. Pour la seconde nonce, request/response/ready/invocation/process sont présents, réguliers et sous8MiB ; delivered.json est absent. Le même delivered existe désormais et a été reçu par SCP séparé.

Le ready distant précède le process de17,146s, au-delà de la garde de15s ; l’ordre source lit delivered avant process. Cela étaye la course entre publication de readiness et clôture des métadonnées de livraison. La corroboration précise du chemin source est confiée au lecteur indépendant. La présence actuelle ne répare pas le reçu historique. Aucun release, replay, reset, correctif ou arrêt n’a été effectué.

Primaires complets, arguments et dates sont préservés ici. Les six réceptions SDK passent toutes ; le catalogue reste distinct de l’archive historique figée. Aucune donnée privée n’est destinée au dépôt public.

"""Closed fifteen-subject R2 protocol; preparation alone never admits inference."""
from __future__ import annotations

import copy
import re

from .core import InfrastructureError

SCOPE = "hpc-forest-matrix15-native-max-r2"
EFFORT = "max"
MODELS = ("gpt-6.1-sol", "gpt-6-luna", "gpt-6-astra", "gpt-5.6-terra")
SUBJECTS = ("2023-count", "2020-tropical", "2020-quicksort", "2020-permutations", "2020-graph",
            "2021-graph", "2021-metrics", "2021-sokoban", "2021-jacobi", "2022-knn", "2022-sum",
            "2022-nbody", "2022-bucketsort", "2023-sum", "2023-npbonacci")
PROTOCOL_SHA256 = "ae2ccbb8d10f54d022bb95248412d0fba8751b8f1c97196336e6e6b9f1fb08b2"
R1_CONTRACTS_SHA256 = "fd36a6c9bdd35845834053d92b83fa58c688c02f0b6443b7a2edfded96956bdf"
HARNESS_SHA256 = "c9a9e1f25fd6c1ae603b7b29d52f9e4c505a2c5df49fbb0eb1362a5691c4aa1b"
REGISTERED_CELLS = {'forest-r2/gpt-6.1-sol/max/2023-count/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2023-count/seed-23',
                                                  'subject_id': '2023-count',
                                                  'model': 'gpt-6.1-sol',
                                                  'effort': 'max',
                                                  'session_id': '4bb93e081ad042a185b7029f3ade2605'},
 'forest-r2/gpt-6.1-sol/max/2020-tropical/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2020-tropical/seed-23',
                                                     'subject_id': '2020-tropical',
                                                     'model': 'gpt-6.1-sol',
                                                     'effort': 'max',
                                                     'session_id': '30fbb4d81ec247e1b0ad846bed870ac0'},
 'forest-r2/gpt-6.1-sol/max/2020-quicksort/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2020-quicksort/seed-23',
                                                      'subject_id': '2020-quicksort',
                                                      'model': 'gpt-6.1-sol',
                                                      'effort': 'max',
                                                      'session_id': 'f5df6a95c3014f67a9d58132abef8dc5'},
 'forest-r2/gpt-6.1-sol/max/2020-permutations/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2020-permutations/seed-23',
                                                         'subject_id': '2020-permutations',
                                                         'model': 'gpt-6.1-sol',
                                                         'effort': 'max',
                                                         'session_id': 'aae3193954e742379ff3655219145df1'},
 'forest-r2/gpt-6.1-sol/max/2020-graph/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2020-graph/seed-23',
                                                  'subject_id': '2020-graph',
                                                  'model': 'gpt-6.1-sol',
                                                  'effort': 'max',
                                                  'session_id': '134c2e8b7a76436aad939f958e3d8ef1'},
 'forest-r2/gpt-6.1-sol/max/2021-graph/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2021-graph/seed-23',
                                                  'subject_id': '2021-graph',
                                                  'model': 'gpt-6.1-sol',
                                                  'effort': 'max',
                                                  'session_id': '65699e2fb78444f59c1d46a3b212d530'},
 'forest-r2/gpt-6.1-sol/max/2021-metrics/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2021-metrics/seed-23',
                                                    'subject_id': '2021-metrics',
                                                    'model': 'gpt-6.1-sol',
                                                    'effort': 'max',
                                                    'session_id': 'cd1a73293fe64fd6b7b686b4f626ee9a'},
 'forest-r2/gpt-6.1-sol/max/2021-sokoban/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2021-sokoban/seed-23',
                                                    'subject_id': '2021-sokoban',
                                                    'model': 'gpt-6.1-sol',
                                                    'effort': 'max',
                                                    'session_id': 'cc8c458e1b0a4aa2b770ce9ece03b73f'},
 'forest-r2/gpt-6.1-sol/max/2021-jacobi/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2021-jacobi/seed-23',
                                                   'subject_id': '2021-jacobi',
                                                   'model': 'gpt-6.1-sol',
                                                   'effort': 'max',
                                                   'session_id': '708751d714aa4f9cb23401875df71fc9'},
 'forest-r2/gpt-6.1-sol/max/2022-knn/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2022-knn/seed-23',
                                                'subject_id': '2022-knn',
                                                'model': 'gpt-6.1-sol',
                                                'effort': 'max',
                                                'session_id': '0e264ca49bf34b699d3afddcbf2162b3'},
 'forest-r2/gpt-6.1-sol/max/2022-sum/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2022-sum/seed-23',
                                                'subject_id': '2022-sum',
                                                'model': 'gpt-6.1-sol',
                                                'effort': 'max',
                                                'session_id': 'e2316329ce3a46f0a50fd49e6041b493'},
 'forest-r2/gpt-6.1-sol/max/2022-nbody/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2022-nbody/seed-23',
                                                  'subject_id': '2022-nbody',
                                                  'model': 'gpt-6.1-sol',
                                                  'effort': 'max',
                                                  'session_id': '637614a8cb0f4658a8060a7e3bcf685f'},
 'forest-r2/gpt-6.1-sol/max/2022-bucketsort/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2022-bucketsort/seed-23',
                                                       'subject_id': '2022-bucketsort',
                                                       'model': 'gpt-6.1-sol',
                                                       'effort': 'max',
                                                       'session_id': 'b387718bc8814a9d84a5f2384066f152'},
 'forest-r2/gpt-6.1-sol/max/2023-sum/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2023-sum/seed-23',
                                                'subject_id': '2023-sum',
                                                'model': 'gpt-6.1-sol',
                                                'effort': 'max',
                                                'session_id': '929ffe5e90b64af19be1776cd6d44ac4'},
 'forest-r2/gpt-6.1-sol/max/2023-npbonacci/seed-23': {'cell_key': 'forest-r2/gpt-6.1-sol/max/2023-npbonacci/seed-23',
                                                      'subject_id': '2023-npbonacci',
                                                      'model': 'gpt-6.1-sol',
                                                      'effort': 'max',
                                                      'session_id': '55b9068bd1d0438c806c481cd965840f'},
 'forest-r2/gpt-6-luna/max/2023-count/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2023-count/seed-23',
                                                 'subject_id': '2023-count',
                                                 'model': 'gpt-6-luna',
                                                 'effort': 'max',
                                                 'session_id': '32212eb983d54451b53b37c4f5b6d694'},
 'forest-r2/gpt-6-luna/max/2020-tropical/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2020-tropical/seed-23',
                                                    'subject_id': '2020-tropical',
                                                    'model': 'gpt-6-luna',
                                                    'effort': 'max',
                                                    'session_id': 'ebeb67659ad44613a10701bdd3573af9'},
 'forest-r2/gpt-6-luna/max/2020-quicksort/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2020-quicksort/seed-23',
                                                     'subject_id': '2020-quicksort',
                                                     'model': 'gpt-6-luna',
                                                     'effort': 'max',
                                                     'session_id': '9a681c2826854a4b885e94c5e6243f0a'},
 'forest-r2/gpt-6-luna/max/2020-permutations/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2020-permutations/seed-23',
                                                        'subject_id': '2020-permutations',
                                                        'model': 'gpt-6-luna',
                                                        'effort': 'max',
                                                        'session_id': '3cf4e33674274bd9a7796526c2927db4'},
 'forest-r2/gpt-6-luna/max/2020-graph/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2020-graph/seed-23',
                                                 'subject_id': '2020-graph',
                                                 'model': 'gpt-6-luna',
                                                 'effort': 'max',
                                                 'session_id': 'efd382d17db840bc9287c85c45012f58'},
 'forest-r2/gpt-6-luna/max/2021-graph/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2021-graph/seed-23',
                                                 'subject_id': '2021-graph',
                                                 'model': 'gpt-6-luna',
                                                 'effort': 'max',
                                                 'session_id': 'de074d7aa73d4340aa228450cb6c2926'},
 'forest-r2/gpt-6-luna/max/2021-metrics/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2021-metrics/seed-23',
                                                   'subject_id': '2021-metrics',
                                                   'model': 'gpt-6-luna',
                                                   'effort': 'max',
                                                   'session_id': 'ed524a3276d444f0b5935e8fbd7432f3'},
 'forest-r2/gpt-6-luna/max/2021-sokoban/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2021-sokoban/seed-23',
                                                   'subject_id': '2021-sokoban',
                                                   'model': 'gpt-6-luna',
                                                   'effort': 'max',
                                                   'session_id': 'c3483a526de04ba49a6af31cb4432d39'},
 'forest-r2/gpt-6-luna/max/2021-jacobi/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2021-jacobi/seed-23',
                                                  'subject_id': '2021-jacobi',
                                                  'model': 'gpt-6-luna',
                                                  'effort': 'max',
                                                  'session_id': 'f175dd8739dd4ea5bdd61906aafa6629'},
 'forest-r2/gpt-6-luna/max/2022-knn/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2022-knn/seed-23',
                                               'subject_id': '2022-knn',
                                               'model': 'gpt-6-luna',
                                               'effort': 'max',
                                               'session_id': 'abd3b70deb874e64a4a269bc58b4e67e'},
 'forest-r2/gpt-6-luna/max/2022-sum/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2022-sum/seed-23',
                                               'subject_id': '2022-sum',
                                               'model': 'gpt-6-luna',
                                               'effort': 'max',
                                               'session_id': '3e57477be8ef4bd1b6acdc47d99ce564'},
 'forest-r2/gpt-6-luna/max/2022-nbody/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2022-nbody/seed-23',
                                                 'subject_id': '2022-nbody',
                                                 'model': 'gpt-6-luna',
                                                 'effort': 'max',
                                                 'session_id': '53a8ebf343774f3f9c39072711225b7f'},
 'forest-r2/gpt-6-luna/max/2022-bucketsort/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2022-bucketsort/seed-23',
                                                      'subject_id': '2022-bucketsort',
                                                      'model': 'gpt-6-luna',
                                                      'effort': 'max',
                                                      'session_id': 'eeae618c8d4a4c5d8debf457b1f71a0d'},
 'forest-r2/gpt-6-luna/max/2023-sum/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2023-sum/seed-23',
                                               'subject_id': '2023-sum',
                                               'model': 'gpt-6-luna',
                                               'effort': 'max',
                                               'session_id': '466fa85de92a4f43bee6aa5fb06d383f'},
 'forest-r2/gpt-6-luna/max/2023-npbonacci/seed-23': {'cell_key': 'forest-r2/gpt-6-luna/max/2023-npbonacci/seed-23',
                                                     'subject_id': '2023-npbonacci',
                                                     'model': 'gpt-6-luna',
                                                     'effort': 'max',
                                                     'session_id': '4356af9529cd4350af3dd1f256e41273'},
 'forest-r2/gpt-6-astra/max/2023-count/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2023-count/seed-23',
                                                  'subject_id': '2023-count',
                                                  'model': 'gpt-6-astra',
                                                  'effort': 'max',
                                                  'session_id': '90dc34c1c17d4eddb084e38047fb3678'},
 'forest-r2/gpt-6-astra/max/2020-tropical/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2020-tropical/seed-23',
                                                     'subject_id': '2020-tropical',
                                                     'model': 'gpt-6-astra',
                                                     'effort': 'max',
                                                     'session_id': '2752e48296044ac4b5fc540d35a66424'},
 'forest-r2/gpt-6-astra/max/2020-quicksort/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2020-quicksort/seed-23',
                                                      'subject_id': '2020-quicksort',
                                                      'model': 'gpt-6-astra',
                                                      'effort': 'max',
                                                      'session_id': '8f069a43f8104f498abf0e2132958db6'},
 'forest-r2/gpt-6-astra/max/2020-permutations/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2020-permutations/seed-23',
                                                         'subject_id': '2020-permutations',
                                                         'model': 'gpt-6-astra',
                                                         'effort': 'max',
                                                         'session_id': '930691afa71d442ea0d2a82be19e7fbc'},
 'forest-r2/gpt-6-astra/max/2020-graph/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2020-graph/seed-23',
                                                  'subject_id': '2020-graph',
                                                  'model': 'gpt-6-astra',
                                                  'effort': 'max',
                                                  'session_id': '2986e54ae1874d4d9f63b86d58177ac2'},
 'forest-r2/gpt-6-astra/max/2021-graph/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2021-graph/seed-23',
                                                  'subject_id': '2021-graph',
                                                  'model': 'gpt-6-astra',
                                                  'effort': 'max',
                                                  'session_id': '43bd9f9215854030a1817703168ea12b'},
 'forest-r2/gpt-6-astra/max/2021-metrics/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2021-metrics/seed-23',
                                                    'subject_id': '2021-metrics',
                                                    'model': 'gpt-6-astra',
                                                    'effort': 'max',
                                                    'session_id': 'a6fb243d7d2c41d1bc55ca9ffc7a41db'},
 'forest-r2/gpt-6-astra/max/2021-sokoban/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2021-sokoban/seed-23',
                                                    'subject_id': '2021-sokoban',
                                                    'model': 'gpt-6-astra',
                                                    'effort': 'max',
                                                    'session_id': 'cf68e87a9a4a4a6389bd4fcd085e7959'},
 'forest-r2/gpt-6-astra/max/2021-jacobi/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2021-jacobi/seed-23',
                                                   'subject_id': '2021-jacobi',
                                                   'model': 'gpt-6-astra',
                                                   'effort': 'max',
                                                   'session_id': '155dbd681c8a4abda79867a0957b01d8'},
 'forest-r2/gpt-6-astra/max/2022-knn/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2022-knn/seed-23',
                                                'subject_id': '2022-knn',
                                                'model': 'gpt-6-astra',
                                                'effort': 'max',
                                                'session_id': 'dfe6f0d7ea4c4a8fb20431bd1e598dc6'},
 'forest-r2/gpt-6-astra/max/2022-sum/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2022-sum/seed-23',
                                                'subject_id': '2022-sum',
                                                'model': 'gpt-6-astra',
                                                'effort': 'max',
                                                'session_id': 'adbcf9c670a14889961a99c5a5570c0d'},
 'forest-r2/gpt-6-astra/max/2022-nbody/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2022-nbody/seed-23',
                                                  'subject_id': '2022-nbody',
                                                  'model': 'gpt-6-astra',
                                                  'effort': 'max',
                                                  'session_id': '9c1a4dece11b4d65bbdc188b7a6d15ce'},
 'forest-r2/gpt-6-astra/max/2022-bucketsort/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2022-bucketsort/seed-23',
                                                       'subject_id': '2022-bucketsort',
                                                       'model': 'gpt-6-astra',
                                                       'effort': 'max',
                                                       'session_id': '0fe045084abb41e7835896b0892897d1'},
 'forest-r2/gpt-6-astra/max/2023-sum/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2023-sum/seed-23',
                                                'subject_id': '2023-sum',
                                                'model': 'gpt-6-astra',
                                                'effort': 'max',
                                                'session_id': '6fb07fc6f40d4c59834576bc6b4d454e'},
 'forest-r2/gpt-6-astra/max/2023-npbonacci/seed-23': {'cell_key': 'forest-r2/gpt-6-astra/max/2023-npbonacci/seed-23',
                                                      'subject_id': '2023-npbonacci',
                                                      'model': 'gpt-6-astra',
                                                      'effort': 'max',
                                                      'session_id': 'a81c181b1b664ad08a320a165a13c61e'},
 'forest-r2/gpt-5.6-terra/max/2023-count/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2023-count/seed-23',
                                                    'subject_id': '2023-count',
                                                    'model': 'gpt-5.6-terra',
                                                    'effort': 'max',
                                                    'session_id': 'a3440e670f5b4d158b5d57f69c7a3bdf'},
 'forest-r2/gpt-5.6-terra/max/2020-tropical/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2020-tropical/seed-23',
                                                       'subject_id': '2020-tropical',
                                                       'model': 'gpt-5.6-terra',
                                                       'effort': 'max',
                                                       'session_id': '008bc6e6d53f40729ceca70a6858782b'},
 'forest-r2/gpt-5.6-terra/max/2020-quicksort/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2020-quicksort/seed-23',
                                                        'subject_id': '2020-quicksort',
                                                        'model': 'gpt-5.6-terra',
                                                        'effort': 'max',
                                                        'session_id': 'b94e1bf3921d42aeb8db5b3d39b5beb8'},
 'forest-r2/gpt-5.6-terra/max/2020-permutations/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2020-permutations/seed-23',
                                                           'subject_id': '2020-permutations',
                                                           'model': 'gpt-5.6-terra',
                                                           'effort': 'max',
                                                           'session_id': 'fdbf2c5a4a3f4eee91801ce31d54585e'},
 'forest-r2/gpt-5.6-terra/max/2020-graph/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2020-graph/seed-23',
                                                    'subject_id': '2020-graph',
                                                    'model': 'gpt-5.6-terra',
                                                    'effort': 'max',
                                                    'session_id': 'c32883473b6048f79898a30710761b1b'},
 'forest-r2/gpt-5.6-terra/max/2021-graph/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2021-graph/seed-23',
                                                    'subject_id': '2021-graph',
                                                    'model': 'gpt-5.6-terra',
                                                    'effort': 'max',
                                                    'session_id': '95fe97f192e54b1d863c1edc6cab198d'},
 'forest-r2/gpt-5.6-terra/max/2021-metrics/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2021-metrics/seed-23',
                                                      'subject_id': '2021-metrics',
                                                      'model': 'gpt-5.6-terra',
                                                      'effort': 'max',
                                                      'session_id': '42f6f51d92444a7abff6346457bd61b0'},
 'forest-r2/gpt-5.6-terra/max/2021-sokoban/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2021-sokoban/seed-23',
                                                      'subject_id': '2021-sokoban',
                                                      'model': 'gpt-5.6-terra',
                                                      'effort': 'max',
                                                      'session_id': 'ccee2d7ec8a04e54aa2f7fdcefe0ac45'},
 'forest-r2/gpt-5.6-terra/max/2021-jacobi/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2021-jacobi/seed-23',
                                                     'subject_id': '2021-jacobi',
                                                     'model': 'gpt-5.6-terra',
                                                     'effort': 'max',
                                                     'session_id': '3480cf3477df430bb806f44b05fca73a'},
 'forest-r2/gpt-5.6-terra/max/2022-knn/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2022-knn/seed-23',
                                                  'subject_id': '2022-knn',
                                                  'model': 'gpt-5.6-terra',
                                                  'effort': 'max',
                                                  'session_id': 'c971abfcc8764c42bf05daf711ceb644'},
 'forest-r2/gpt-5.6-terra/max/2022-sum/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2022-sum/seed-23',
                                                  'subject_id': '2022-sum',
                                                  'model': 'gpt-5.6-terra',
                                                  'effort': 'max',
                                                  'session_id': '4a7a6aed94d44935a8ebd7359eecd12e'},
 'forest-r2/gpt-5.6-terra/max/2022-nbody/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2022-nbody/seed-23',
                                                    'subject_id': '2022-nbody',
                                                    'model': 'gpt-5.6-terra',
                                                    'effort': 'max',
                                                    'session_id': '4a268b132da24e4988a3f7c21f526ecd'},
 'forest-r2/gpt-5.6-terra/max/2022-bucketsort/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2022-bucketsort/seed-23',
                                                         'subject_id': '2022-bucketsort',
                                                         'model': 'gpt-5.6-terra',
                                                         'effort': 'max',
                                                         'session_id': 'cafcd0cc2c44446c9c0d050e84d6d160'},
 'forest-r2/gpt-5.6-terra/max/2023-sum/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2023-sum/seed-23',
                                                  'subject_id': '2023-sum',
                                                  'model': 'gpt-5.6-terra',
                                                  'effort': 'max',
                                                  'session_id': '88fbf8bf44504a0788033e22c6e9cd9a'},
 'forest-r2/gpt-5.6-terra/max/2023-npbonacci/seed-23': {'cell_key': 'forest-r2/gpt-5.6-terra/max/2023-npbonacci/seed-23',
                                                        'subject_id': '2023-npbonacci',
                                                        'model': 'gpt-5.6-terra',
                                                        'effort': 'max',
                                                        'session_id': '47a32bb8992145f6a2b2de75d280c409'}}
BUDGETS = {"wall_seconds": 1800, "tokens": 1500000, "shared_generation_seconds": 600,
           "confirmation_seconds": 120, "maximum_program_missions": 8, "maximum_mother_calls": 2,
           "search_repetitions": 3, "final_confirmations": 5, "seed": 23, "minimum_gain_fraction": 0.03}
TARGET = {"architecture": "aarch64", "cpu_cores": 4, "memory_mib": 16384, "gpus": 0}
CELL_FIELDS = {"cell_key", "subject_id", "model", "effort", "session_id"}
SUBJECT_FIELDS = {"subject_id", "official_preparation_path", "preparation_sha256", "r1_contract_ref", "statement_ref",
                  "prepared_contract_ref", "qualification_ref", "reception_ref", "config"}
PLAN_FIELDS = {"schema", "scope_id", "protocol", "models", "efforts", "subjects", "cells",
               "subject_bindings", "source_zip_sha256", "runtime_manifest", "preparation_manifest", "artifact_aliases",
               "r1_contracts", "harness", "primes_release", "maximum_native_workers_total",
               "maximum_cells_per_authorization", "budgets_per_cell", "target", "automatic_extension",
               "scientific_contract", "exclusive_deadline_utc", "reception_audit_reserve_seconds"}


def need(ok, message):
    if not ok:
        raise InfrastructureError(message)


def sha_value(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def reference(value):
    return (isinstance(value, dict) and set(value) == {"path", "sha256"}
            and isinstance(value["path"], str) and bool(value["path"])
            and sha_value(value["sha256"]))


def validate_cell(cell):
    need(isinstance(cell, dict) and set(cell) == CELL_FIELDS, "Exact matrix cell fields required")
    key = cell["cell_key"]
    need(key in REGISTERED_CELLS and cell == REGISTERED_CELLS[key],
         "Only the sixty registered MAX subject/model/session identities are permitted")
    return copy.deepcopy(cell)


def validate_plan(plan):
    """Validate the immutable upstream plan; final receipts belong to its authorization."""
    need(isinstance(plan, dict) and set(plan) == PLAN_FIELDS, "Exact matrix15 plan fields required")
    need(plan["schema"] == "hpc-forest-matrix15-native-max-plan-v2" and plan["scope_id"] == SCOPE,
         "Wrong matrix15 scope/schema")
    need(plan["models"] == list(MODELS) and plan["efforts"] == [EFFORT]
         and plan["subjects"] == list(SUBJECTS), "Closed four MAX models and fifteen subjects required")
    cells = plan["cells"]
    need(isinstance(cells, list) and len(cells) == 60, "Exactly sixty cells required")
    validated = [validate_cell(cell) for cell in cells]
    need(len({cell["cell_key"] for cell in validated}) == 60
         and {cell["cell_key"] for cell in validated} == set(REGISTERED_CELLS)
         and len({cell["session_id"] for cell in validated}) == 60,
         "Repeated or missing matrix cell/session")
    need(type(plan["maximum_native_workers_total"]) is int and plan["maximum_native_workers_total"] == 4
         and type(plan["maximum_cells_per_authorization"]) is int and plan["maximum_cells_per_authorization"] == 1
         and plan["automatic_extension"] is False, "A single-cell admission under global cap4 is required")
    need(plan["budgets_per_cell"] == BUDGETS and plan["target"] == TARGET
         and all(type(plan["budgets_per_cell"][key]) is type(value) for key, value in BUDGETS.items())
         and all(type(plan["target"][key]) is type(value) for key, value in TARGET.items()),
         "Scientific budgets or allocated target changed")
    need(plan["exclusive_deadline_utc"] == "2026-10-31T23:00:00Z"
         and type(plan["reception_audit_reserve_seconds"]) is int
         and plan["reception_audit_reserve_seconds"] == 10800, "Exclusive deadline/reserve changed")
    need(plan["scientific_contract"] == "exact-R1-harness-mixed-calibration-only-excluded",
         "R1 mixed harness contract must remain explicit")
    for field in ("protocol", "runtime_manifest", "preparation_manifest", "r1_contracts", "harness", "artifact_aliases"):
        need(reference(plan[field]), "Missing hash-bound matrix plan reference: " + field)
    need(plan["protocol"]["sha256"] == PROTOCOL_SHA256
         and plan["r1_contracts"]["sha256"] == R1_CONTRACTS_SHA256
         and plan["harness"]["sha256"] == HARNESS_SHA256 and sha_value(plan["source_zip_sha256"]),
         "Registered protocol/R1/harness/source bindings changed")
    need(plan["primes_release"] is None or reference(plan["primes_release"]), "Invalid primes release reference")
    bindings = plan["subject_bindings"]
    need(isinstance(bindings, dict) and set(bindings) == set(SUBJECTS), "Exact fifteen preparation bindings required")
    for key, subject in bindings.items():
        need(isinstance(subject, dict) and set(subject) == SUBJECT_FIELDS and subject["subject_id"] == key,
             "Exact subject preparation binding required")
        need(isinstance(subject["official_preparation_path"], str) and bool(subject["official_preparation_path"])
             and sha_value(subject["preparation_sha256"]) and isinstance(subject["config"], dict)
             and reference(subject["r1_contract_ref"]) and reference(subject["prepared_contract_ref"])
             and reference(subject["statement_ref"]),
             "Prepared official subject/config/contracts are missing")
        need(all(subject[name] is None for name in ("qualification_ref", "reception_ref")),
             "Final qualification/reception references belong only to the downstream authorization")
        codex = subject["config"].get("codex", {})
        need(isinstance(codex, dict) and codex.get("model") == "{cell.model}"
             and codex.get("reasoning_effort") == EFFORT,
             "Per-subject configuration requires the closed cell.model placeholder and MAX")
    return copy.deepcopy(plan)


def resolve_subject(plan, cell_key):
    plan = validate_plan(plan)
    need(cell_key in REGISTERED_CELLS, "Unknown matrix15 cell")
    cell = REGISTERED_CELLS[cell_key]
    return {**copy.deepcopy(plan["subject_bindings"][cell["subject_id"]]), **copy.deepcopy(cell)}


def assert_r1_pair_contract(reference_contract, received_contract):
    """Ignore only local reference calibration; preserve inputs/oracles/compiler/options."""
    def comparable(value):
        need(isinstance(value, dict), "Contract must be a JSON object")
        value = copy.deepcopy(value)
        if isinstance(value.get("benchmark"), dict):
            value["benchmark"].pop("reference_seconds", None)
        return value
    need(comparable(reference_contract) == comparable(received_contract),
         "R1 paired input/oracle/domain/compiler contract differs beyond local calibration")

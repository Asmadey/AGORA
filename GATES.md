# Gates: личные ценности из ответа респондента

OWNS: GATES.md, services/agent-core/agent_core/persona/generator.py, services/agent-core/agent_core/persona/value_source.py, services/agent-core/agent_core/matching/finder.py, services/agent-core/agent_core/portraits/distill.py, services/agent-core/tests/test_personal_values_source.py, evals/tests/test_task25_matching.py, data/grounding/corpus.meta.json

Scope: брать частоты личных ценностей только из личного вопроса корпуса, сопоставлять ответы с каноном и сохранить контракт генерации персон.

- [x] G0: ворота имеют проверяемую структуру
  CHECK: node .claude/skills/unlazy/scripts/gate-lint.mjs GATES.md
  EXPECT: LINT OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=62f9b2f96b674ee169b65e92260aa9abecc87fcb494c1f98077ea878d6974f55; exit=0; EXPECT=matched; output-sha256=48630b7361dd44ee870917b12c3d19b9d7bdea738aaca16bb04d4cab83b772d2; output-bytes=8; shell=/bin/sh; cwd=/private/tmp/AGORA-values28; path=b4d96a1db5ae/30 entries

- [x] G1: реальные частоты личного вопроса совпадают с ожидаемыми
  CHECK: PYTHONPATH=services/agent-core /Users/asmadey/.venv/main/bin/pytest -q services/agent-core/tests/test_personal_values_source.py -k personal_answer_counts && echo G1_PERSONAL_VALUES_COUNTS_OK
  EXPECT: G1_PERSONAL_VALUES_COUNTS_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=c4c4d58f23c0131334af7edc94ef3a0e2be4293249bc05790445bf5e5663ea06; exit=0; EXPECT=matched; output-sha256=2d281ef068b5a4c1d35f372d5219155505b2b243b0732bb7ce032ccb183d6f31; output-bytes=109; shell=/bin/sh; cwd=/private/tmp/AGORA-values28; path=b4d96a1db5ae/30 entries

- [x] G2: записи без личного вопроса исключаются, а ответ с запятыми остаётся одной атомарной строкой
  CHECK: PYTHONPATH=services/agent-core /Users/asmadey/.venv/main/bin/pytest -q services/agent-core/tests/test_personal_values_source.py -k personal_answer_source && echo G2_PERSONAL_VALUES_SOURCE_OK
  EXPECT: G2_PERSONAL_VALUES_SOURCE_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=d7146b84c9c9b18b953fba98d9b03d748039e0f1b7ba7d443495442cf09deea4; exit=0; EXPECT=matched; output-sha256=f13defe8fe2d62c697ef2dd57810e8259ee35eb5b42c46b458cd02319697b2f7; output-bytes=109; shell=/bin/sh; cwd=/private/tmp/AGORA-values28; path=b4d96a1db5ae/30 entries

- [x] G3: генератор выдаёт ровно пять уникальных канонических ценностей
  CHECK: PYTHONPATH=services/agent-core /Users/asmadey/.venv/main/bin/pytest -q services/agent-core/tests/test_persona_values.py && echo G3_PERSONA_VALUES_OK
  EXPECT: G3_PERSONA_VALUES_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=27223267b4b51470d8eb02485ce461305c3ed903707e67ebdaf661d2c74e9d39; exit=0; EXPECT=matched; output-sha256=9208ac24291f8772a4eb53798ec6d5cc40215491a4b74ebac6e49821a1dce0a7; output-bytes=101; shell=/bin/sh; cwd=/private/tmp/AGORA-values28; path=b4d96a1db5ae/30 entries

- [x] G4: прежний CDD и полный тест источника остаются зелёными
  CHECK: python3 evals/tests/test_task05_persona_generator.py && echo G4_PERSONA_CDD_OK
  EXPECT: G4_PERSONA_CDD_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=03693e660a2145f5397aa29b2b939b2d811fbea14f78bcc6dbf6a12dfc7b1bab; exit=0; EXPECT=matched; output-sha256=7bb7be5b02d4f54cebcbd68bc56b766b799c2d7c0a7be2feff461473029ae7b1; output-bytes=1731; shell=/bin/sh; cwd=/private/tmp/AGORA-values28; path=b4d96a1db5ae/30 entries

- [x] G5: подбор и портрет используют тот же личный источник, а поля персоны не меняются
  CHECK: PYTHONPATH=services/agent-core /Users/asmadey/.venv/main/bin/pytest -q services/agent-core/tests/test_personal_values_source.py -k readers && echo G5_PERSONAL_VALUE_READERS_OK
  EXPECT: G5_PERSONAL_VALUE_READERS_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=ef01daab6800cb36b891bfc3a17033919fcf2ac6fe74f042da3a912e927c13a0; exit=0; EXPECT=matched; output-sha256=37318b03bdb36a7072db6d21d85cbe80b0d5e064e2c7fa5f4eb51eec5519bb3d; output-bytes=109; shell=/bin/sh; cwd=/private/tmp/AGORA-values28; path=b4d96a1db5ae/30 entries

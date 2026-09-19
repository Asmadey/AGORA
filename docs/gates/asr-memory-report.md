# Gates: honest ASR memory report

OWNS: services/agent-core/agent_core/asr/budget.py, services/agent-core/agent_core/pipeline/nodes.py, services/agent-core/tests/test_parallel_asr.py

Scope: сообщение последовательной ASR-ветки должно описывать один замер памяти, все слагаемые решения и сохранять параллельную ветку.

- [x] G1: degraded сообщает память, измеренную в момент выбора последовательной ветки
  CHECK: python3 -m pytest tests/test_parallel_asr.py -k memory_report_uses_decision_sample -o addopts=
  EXPECT: 1 passed
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=b1bdb9dae6f98345a8cab6c6399fb2750ad753026955b822757590a52fb90582; exit=0; EXPECT=matched; output-sha256=495ec5639b4b250a0c904293288a4e9daa3839416bd70b900c0b0cd9bf30e04c; output-bytes=469; shell=/bin/sh; cwd=/private/tmp/AGORA-mem/services/agent-core; path=7e96d27e8d7b/31 entries

- [x] G2: degraded содержит имя модели, оба пика, запас и итоговую потребность
  CHECK: python3 -m pytest tests/test_parallel_asr.py -k memory_report_lists_all_budget_parts -o addopts=
  EXPECT: 1 passed
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=d232e918902d74a16649cb6fc42213288fc1b4e1c11221d1d05487085ae64c73; exit=0; EXPECT=matched; output-sha256=b2855e4c8b20162dc8dc6a39a34bcce00578446e8932c2e7298851641224c1d5; output-bytes=469; shell=/bin/sh; cwd=/private/tmp/AGORA-mem/services/agent-core; path=7e96d27e8d7b/31 entries

- [x] G3: решение и сообщение используют один замер available_mb
  CHECK: python3 -m pytest tests/test_parallel_asr.py -k memory_report_uses_one_memory_sample -o addopts=
  EXPECT: 1 passed
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=48f2f2a956d4883936af07f7fe7f168b6baf1468d9349115275ca15ba62d6abe; exit=0; EXPECT=matched; output-sha256=48307b2e5d2885a90054d2fe3375c1f36f62e3a0ba714a295179d5786f89aeaa; output-bytes=469; shell=/bin/sh; cwd=/private/tmp/AGORA-mem/services/agent-core; path=7e96d27e8d7b/31 entries

- [x] G4: достаточная память сохраняет параллельное выполнение без строки о последовательной очереди
  CHECK: python3 -m pytest tests/test_parallel_asr.py -k both_halves_overlap_in_time -o addopts=
  EXPECT: 1 passed
  CWD: services/agent-core
  EVIDENCE: automatic-evidence=v1; definition-sha256=184565e96fa3138dad8c52296e24db068a9246fc48675d2b552bbe4a2f74b61f; exit=0; EXPECT=matched; output-sha256=6fbf35a1b27188a3361582f522170f20e5b01a594ce03bf9f674e38e9266a94a; output-bytes=469; shell=/bin/sh; cwd=/private/tmp/AGORA-mem/services/agent-core; path=7e96d27e8d7b/31 entries

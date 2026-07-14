# Stage 31 Trace-Guided Performance Benchmark

```json
{
  "schema_version": "1.0",
  "stage": "stage-31-trace-guided-performance",
  "artifact_role": "baseline",
  "evaluated_at": "2026-07-14T02:48:21.573143Z",
  "git_revision": "6b75d1c89072318cf4cfea4465689eb7fad1ae22",
  "input_sha256": "252b547ba756af6d71fea1f8ce7ee7d448c6bf67172c4bbeb136116d937cbdca",
  "environment": {
    "os": "Darwin",
    "architecture": "arm64",
    "python": "3.11.15",
    "boundary": "offline benchmark; not production SLA"
  },
  "provider": {
    "requested_provider": "deepseek",
    "effective_provider": "deepseek",
    "requested_model": "deepseek-v4-flash",
    "effective_model": "deepseek-v4-flash"
  },
  "rag": {
    "requested_embedding_backend": "bge_m3",
    "effective_embedding_backend": "bge_m3",
    "retrieval_mode": "dense"
  },
  "run_plan": {
    "cold_runs": 1,
    "warmup_runs": 1,
    "measured_runs": 20,
    "complete_measured_count": 20
  },
  "trust": {
    "trusted": true,
    "reasons": [],
    "environment_gap": null
  },
  "trace": {
    "completeness_numerator": 20,
    "completeness_denominator": 20,
    "completeness_rate": 1.0,
    "samples": [
      {
        "trace_id": "3e5bf706-b763-4058-bafb-268c3c68926c",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "7ec2ec98-17cb-4d45-bb0c-f979f843842b",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "863735fd-fc78-4659-87e4-b9d2a854c298",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "8a19f9c6-df31-4f61-88ed-1ae653ef12b5",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "e9d4a3f0-1930-4039-a23c-87a96f20587b",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "ce746eb9-eab3-40f7-a981-62e7ea14ca14",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "7a376f7a-ec19-4b79-a093-fc59822b371d",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "d8832ce9-19e0-418e-9df7-963ff672929d",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "34a1daa2-8a30-4ce2-9666-cf7aea1a6a47",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "e6e68daa-e51c-42c7-b4ac-b4f60ac87cd7",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "21a6a64c-4ad2-4e72-8fb9-6b001ac7676f",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "de359321-9928-4cfa-8ff8-bf20a1e25231",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "f61a947a-08a4-4208-856f-9bd575bc8868",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "ea36a230-0d94-48d6-a9aa-4b94acbd5121",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "e0312f1d-ef48-4ff8-9e34-4346cfd4390e",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "a2b3500e-5514-4b1b-8616-51b0dc6cf845",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "14cc3deb-b902-47af-902b-181e51ab5086",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "1806cb4b-41b1-487c-b35e-126ae4afd506",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      },
      {
        "trace_id": "5070a9b4-20f5-49c9-8f7f-c0c19a49d0b6",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 2
      },
      {
        "trace_id": "06648312-acb2-4cd2-8202-e6837c8d3a0c",
        "is_complete": true,
        "failure_reason": null,
        "root_span": 1,
        "terminal_span": 1,
        "ext_spans": 1,
        "rag_spans": 1,
        "agent_count": 2,
        "tool_count": 1
      }
    ]
  },
  "contract_observations": [
    {
      "trace_id": "3e5bf706-b763-4058-bafb-268c3c68926c",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "7ec2ec98-17cb-4d45-bb0c-f979f843842b",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "863735fd-fc78-4659-87e4-b9d2a854c298",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "8a19f9c6-df31-4f61-88ed-1ae653ef12b5",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "e9d4a3f0-1930-4039-a23c-87a96f20587b",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "ce746eb9-eab3-40f7-a981-62e7ea14ca14",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "7a376f7a-ec19-4b79-a093-fc59822b371d",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "d8832ce9-19e0-418e-9df7-963ff672929d",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "34a1daa2-8a30-4ce2-9666-cf7aea1a6a47",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "e6e68daa-e51c-42c7-b4ac-b4f60ac87cd7",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "21a6a64c-4ad2-4e72-8fb9-6b001ac7676f",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "de359321-9928-4cfa-8ff8-bf20a1e25231",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "f61a947a-08a4-4208-856f-9bd575bc8868",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "ea36a230-0d94-48d6-a9aa-4b94acbd5121",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "e0312f1d-ef48-4ff8-9e34-4346cfd4390e",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "a2b3500e-5514-4b1b-8616-51b0dc6cf845",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "14cc3deb-b902-47af-902b-181e51ab5086",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "1806cb4b-41b1-487c-b35e-126ae4afd506",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    },
    {
      "trace_id": "5070a9b4-20f5-49c9-8f7f-c0c19a49d0b6",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 2,
        "path": "L1->L2->HUMAN",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules",
        "load_confirmed_cases"
      ]
    },
    {
      "trace_id": "06648312-acb2-4cd2-8202-e6837c8d3a0c",
      "business_decision": "PENDING_HUMAN",
      "next_action": "PENDING_HUMAN",
      "rag": {
        "outcome": "RESULT",
        "result_count": 5,
        "evidence_ids": [
          "bank_enterprise_amount_mismatch_advanced_005",
          "bank_enterprise_amount_mismatch_playbook_001",
          "bank_enterprise_exact_match_playbook_003",
          "bank_enterprise_narrative_mismatch_advanced_004",
          "bank_enterprise_narrative_mismatch_playbook_001"
        ]
      },
      "fallback": {
        "level": 0,
        "path": "L1",
        "terminal_type": "FALLBACK",
        "terminal_outcome": "PENDING_HUMAN"
      },
      "trace_invariants_valid": true,
      "agent_calls": [
        "ExtractionAgent",
        "AuditAgent"
      ],
      "tool_calls": [
        "search_rules"
      ]
    }
  ],
  "latency": {
    "cold_observations": [
      {
        "e2e_ms": 17998.439,
        "extraction_ms": 6842,
        "rag_ms": 6660
      }
    ],
    "end_to_end": {
      "avg_latency_ms": 9743.837,
      "p50_latency_ms": 9462.284,
      "p95_latency_ms": 13621.027,
      "min_latency_ms": 6811.572,
      "max_latency_ms": 13621.027,
      "samples_ms": [
        13032.278,
        8335.266,
        8158.804,
        11191.36,
        9039.068,
        10976.847,
        10577.074,
        10100.944,
        11727.207,
        10145.844,
        6811.572,
        7406.46,
        8258.62,
        13621.027,
        9060.758,
        9486.531,
        9242.473,
        9789.266,
        9438.037,
        8477.313
      ]
    },
    "extraction_agent": {
      "avg_latency_ms": 3281.65,
      "p50_latency_ms": 3294.0,
      "p95_latency_ms": 4944,
      "min_latency_ms": 1845,
      "max_latency_ms": 4944,
      "samples_ms": [
        4944,
        3305,
        3283,
        2023,
        3120,
        1845,
        4554,
        3657,
        2978,
        3827,
        2595,
        2574,
        2349,
        3675,
        3139,
        2603,
        4004,
        3913,
        3581,
        3664
      ]
    },
    "rag_search": {
      "avg_latency_ms": 66.75,
      "p50_latency_ms": 66.0,
      "p95_latency_ms": 89,
      "min_latency_ms": 58,
      "max_latency_ms": 89,
      "samples_ms": [
        66,
        71,
        68,
        65,
        65,
        67,
        65,
        67,
        64,
        58,
        63,
        68,
        66,
        64,
        68,
        89,
        66,
        65,
        67,
        63
      ]
    }
  },
  "theory": {
    "per_run_predicted_parallel_e2e_ms": [
      12966.278,
      8264.266,
      8090.804,
      11126.36,
      8974.068,
      10909.847,
      10512.074,
      10033.944,
      11663.207,
      10087.844,
      6748.572,
      7338.46,
      8192.62,
      13557.027,
      8992.758,
      9397.531,
      9176.473,
      9724.266,
      9371.037,
      8414.313
    ],
    "actual_warm_p95_ms": 13621.027,
    "predicted_warm_p95_ms": 13557.027,
    "theoretical_p95_improvement_pct": 0.47,
    "formula": "actual_e2e_ms - extraction_duration_ms - rag_duration_ms + max(extraction_duration_ms, rag_duration_ms)"
  },
  "independence": {
    "data_dependency": {
      "finding": "safe",
      "detail": "RAG query is built from scenario_type, error_type, exception_branch, and amounts via _build_rag_query(); does not read extraction_result. Static code analysis confirms data independence.",
      "source": "static_code_analysis"
    },
    "shared_state": {
      "finding": "unknown",
      "detail": "In serial runtime there is no concurrent access. For a parallel candidate, this assessment is conditional on workers receiving read-only inputs and returning results without modifying shared ReconciliationState, Trace recorder, SSE emitter, or persistent state. This has NOT been verified in running code.",
      "source": "static_analysis_unverified"
    },
    "failure_order": {
      "finding": "unsafe",
      "detail": "In serial runtime, Extraction failure causes early return before RAG. In a parallel candidate, the failure of one side while the other is in-flight changes the current side-effect order. No candidate exists to prove fail-closed handling.",
      "source": "static_analysis_unverified"
    },
    "cancellation": {
      "finding": "unbounded",
      "detail": "Synchronous provider/retriever calls may not support hard interrupt. No candidate demonstrates bounded cancellation or proves that work has stopped before run_item returns.",
      "source": "static_analysis_unverified"
    },
    "resource_reclamation": {
      "finding": "unknown",
      "detail": "No candidate thread lifecycle exists, so resource reclamation and the absence of cross-flow background work are not yet proven.",
      "source": "static_analysis_unverified"
    }
  },
  "usage": {
    "logical_agent_calls": 40,
    "logical_tool_calls": 27,
    "provider_transport_attempts": 40,
    "input_tokens": 58960,
    "output_tokens": 14550,
    "total_tokens": 73510,
    "per_successful_run_tokens": 3675
  },
  "cost": {
    "assumptions": "DeepSeek v4 Pro pricing: input $0.89/1M, output $3.45/1M",
    "total_estimated_usd": "0.0383061",
    "per_successful_run_estimated_usd": "0.001915305",
    "unavailable_reason": null
  },
  "reliability": {
    "success_count": 20,
    "failure_count": 0,
    "error_rate": 0.0,
    "error_distribution": {}
  },
  "decision": "no_go",
  "closed_reasons": [
    "independence_gate_failed",
    "theory_pct_0.47_lt_20.0"
  ]
}
```

## Baseline Decision
**Decision**: `no_go`
**Reasons**: ['independence_gate_failed', 'theory_pct_0.47_lt_20.0']

## Identity
- Schema: `1.0`
- Stage: `stage-31-trace-guided-performance`
- Git: `6b75d1c89072318cf4cfea4465689eb7fad1ae22`
- Input SHA256: `252b547ba756af6d71fea1f8ce7ee7d448c6bf67172c4bbeb136116d937cbdca`

## Trust
- Trusted: `True`
- Reasons: []

## Run Plan
- Cold: 1
- Warmup: 1
- Measured: 20
- Complete: 20

## Latency
- E2E P95: 13621.027 ms
- E2E P50: 9462.284 ms

## Theory
- Predicted P95: 13557.027 ms
- Actual P95: 13621.027 ms
- Improvement: 0.47%

## Usage
- Logical Agent calls: 40
- Logical Tool calls: 27
- Provider transport attempts: 40
- Total tokens: 73510

## Cost
- Total: 0.0383061
- Per-run: 0.001915305

## Reliability
- Success: 20
- Failure: 0
- Error Rate: 0.0

## Independence Gate
- **data_dependency**: `safe` — RAG query is built from scenario_type, error_type, exception_branch, and amounts via _build_rag_query(); does not read extraction_result. Static code analysis confirms data independence.
- **shared_state**: `unknown` — In serial runtime there is no concurrent access. For a parallel candidate, this assessment is conditional on workers receiving read-only inputs and returning results without modifying shared ReconciliationState, Trace recorder, SSE emitter, or persistent state. This has NOT been verified in running code.
- **failure_order**: `unsafe` — In serial runtime, Extraction failure causes early return before RAG. In a parallel candidate, the failure of one side while the other is in-flight changes the current side-effect order. No candidate exists to prove fail-closed handling.
- **cancellation**: `unbounded` — Synchronous provider/retriever calls may not support hard interrupt. No candidate demonstrates bounded cancellation or proves that work has stopped before run_item returns.
- **resource_reclamation**: `unknown` — No candidate thread lifecycle exists, so resource reclamation and the absence of cross-flow background work are not yet proven.

CREATE TABLE IF NOT EXISTS t_reconciliation_task (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL UNIQUE,
  task_name VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
  total_bank_rows INT NOT NULL DEFAULT 0,
  total_clear_rows INT NOT NULL DEFAULT 0,
  auto_fixed_rows INT NOT NULL DEFAULT 0,
  pending_ai_rows INT NOT NULL DEFAULT 0,
  pending_human_rows INT NOT NULL DEFAULT 0,
  unresolved_rows INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_status_created (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS t_bank_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  flow_id VARCHAR(64),
  account_no_masked VARCHAR(64),
  customer_name_masked VARCHAR(64),
  amount DECIMAL(18,2) NOT NULL,
  trade_time DATETIME NOT NULL,
  summary VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_flow (task_id, flow_id),
  INDEX idx_task_time (task_id, trade_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS t_clear_transaction (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  flow_id VARCHAR(64),
  channel VARCHAR(32),
  amount DECIMAL(18,2) NOT NULL,
  trade_time DATETIME NOT NULL,
  summary VARCHAR(255),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_flow (task_id, flow_id),
  INDEX idx_task_time (task_id, trade_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS t_reconciliation_queue (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  bank_transaction_id BIGINT NULL,
  clear_transaction_id BIGINT NULL,
  error_type VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_AI',
  risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW',
  retry_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_task_status (task_id, status),
  INDEX idx_error_type (error_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS t_error_ledger (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  queue_id BIGINT NOT NULL,
  task_id VARCHAR(64) NOT NULL,
  error_type VARCHAR(32) NOT NULL,
  discrepancy_amount DECIMAL(18,2) NOT NULL DEFAULT 0.00,
  ai_cleaned_json JSON,
  ai_audit_opinion TEXT,
  rag_source VARCHAR(512),
  handle_status VARCHAR(32) NOT NULL DEFAULT 'UNTREATED',
  handler_username VARCHAR(64),
  handle_remark VARCHAR(255),
  handled_at DATETIME,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_error (task_id, error_type),
  INDEX idx_handle_status (handle_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS t_rag_retrieval_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  task_id VARCHAR(64) NOT NULL,
  queue_id BIGINT,
  query_text TEXT NOT NULL,
  top_k INT NOT NULL,
  best_score DECIMAL(8,4),
  sources JSON,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_task_queue (task_id, queue_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


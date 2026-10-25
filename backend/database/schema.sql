CREATE TABLE IF NOT EXISTS mapping_versions (
  mapping_sha CHAR(64) PRIMARY KEY,
  source_name VARCHAR(255) NOT NULL,
  imported_at DATETIME(6) NOT NULL,
  csv_text MEDIUMTEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS raw_variables (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  mapping_sha CHAR(64) NOT NULL,
  row_number INT NOT NULL,
  sumo_name VARCHAR(512) NOT NULL,
  opc_tag VARCHAR(512) NOT NULL,
  metadata JSON NOT NULL,
  UNIQUE KEY mapping_row (mapping_sha,row_number),
  KEY variable_name (sumo_name(191)),
  FOREIGN KEY (mapping_sha) REFERENCES mapping_versions(mapping_sha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS raw_data (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  batch_id CHAR(36) NOT NULL,
  variable_id BIGINT UNSIGNED NOT NULL,
  acquired_at DATETIME(6) NOT NULL,
  source_timestamp DATETIME(6) NULL,
  server_timestamp DATETIME(6) NULL,
  status_code BIGINT UNSIGNED NULL,
  quality VARCHAR(32) NOT NULL,
  raw_value JSON NULL,
  numeric_value DOUBLE NULL,
  scaled_value DOUBLE NULL,
  error TEXT NULL,
  UNIQUE KEY batch_variable (batch_id,variable_id),
  KEY variable_time (variable_id,acquired_at),
  KEY acquisition_time (acquired_at),
  FOREIGN KEY (variable_id) REFERENCES raw_variables(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS sumo_models (
  model_sha CHAR(64) PRIMARY KEY,
  model_name VARCHAR(255) NOT NULL,
  registered_at DATETIME(6) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS sumo_variables (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  model_sha CHAR(64) NOT NULL,
  variable_name VARCHAR(512) NOT NULL,
  variable_type VARCHAR(64) NOT NULL,
  category VARCHAR(64) NOT NULL,
  unit VARCHAR(255) NOT NULL,
  metadata JSON NOT NULL,
  UNIQUE KEY model_variable (model_sha,variable_name),
  FOREIGN KEY (model_sha) REFERENCES sumo_models(model_sha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS sumo_runs (
  run_id CHAR(36) PRIMARY KEY,
  model_sha CHAR(64) NOT NULL,
  started_at DATETIME(6) NOT NULL,
  run_mode VARCHAR(32) NOT NULL,
  configuration JSON NOT NULL,
  FOREIGN KEY (model_sha) REFERENCES sumo_models(model_sha)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS sumo_samples (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  run_id CHAR(36) NOT NULL,
  simulated_ms BIGINT NOT NULL,
  acquired_at DATETIME(6) NOT NULL,
  sensor_read_at DATETIME(6) NULL,
  UNIQUE KEY run_time (run_id,simulated_ms),
  KEY acquisition_time (acquired_at),
  FOREIGN KEY (run_id) REFERENCES sumo_runs(run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS sumo_values (
  sample_id BIGINT UNSIGNED NOT NULL,
  variable_id BIGINT UNSIGNED NOT NULL,
  value_json JSON NULL,
  numeric_value DOUBLE NULL,
  quality VARCHAR(32) NOT NULL,
  PRIMARY KEY (sample_id,variable_id),
  KEY variable_sample (variable_id,sample_id),
  FOREIGN KEY (sample_id) REFERENCES sumo_samples(id) ON DELETE CASCADE,
  FOREIGN KEY (variable_id) REFERENCES sumo_variables(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE OR REPLACE VIEW `raw data` AS
SELECT r.*, v.sumo_name AS variable, v.opc_tag AS OpcTag,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.IO')) AS IO,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.IOType')) AS IOType,
 v.sumo_name AS SumoName,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.SumoType')) AS SumoType,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.SumoUnit')) AS SumoUnit,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.OpcType')) AS OpcType,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.OpcUnit')) AS OpcUnit,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.IsArray')) AS IsArray,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.Scaling')) AS Scaling,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.Offset')) AS Offset,
 JSON_UNQUOTE(JSON_EXTRACT(v.metadata,'$.Comment')) AS Comment,
 v.mapping_sha, v.row_number, v.metadata
FROM raw_data r JOIN raw_variables v ON v.id=r.variable_id;
CREATE OR REPLACE VIEW `sumo simulation` AS
SELECT s.id AS sample_id,s.run_id,s.simulated_ms,s.simulated_ms/3600000.0 AS time_h,
 s.acquired_at,s.sensor_read_at,v.variable_name AS variable,v.unit,v.category,
 v.variable_type,v.model_sha,d.value_json,d.numeric_value,d.quality
FROM sumo_values d JOIN sumo_samples s ON s.id=d.sample_id
JOIN sumo_variables v ON v.id=d.variable_id;

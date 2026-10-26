CREATE OR REPLACE VIEW `raw data` AS
SELECT r.id,r.batch_id,r.variable_id,
 CONVERT_TZ(r.acquired_at,'+00:00','__DISPLAY_TIMEZONE__') AS acquired_at,
 CONVERT_TZ(r.source_timestamp,'+00:00','__DISPLAY_TIMEZONE__') AS source_timestamp,
 CONVERT_TZ(r.server_timestamp,'+00:00','__DISPLAY_TIMEZONE__') AS server_timestamp,
 r.status_code,r.quality,r.raw_value,r.numeric_value,r.scaled_value,r.error,
 r.acquired_at AS acquired_at_utc,r.source_timestamp AS source_timestamp_utc,
 r.server_timestamp AS server_timestamp_utc,
 LEFT(DATE_FORMAT(CONVERT_TZ(r.acquired_at,'+00:00','__DISPLAY_TIMEZONE__'),'%Y-%m-%d %H:%i:%s.%f'),23) AS plot_time,
 '__DISPLAY_TIMEZONE__' AS display_timezone,
 v.sumo_name AS variable,v.opc_tag AS OpcTag,
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
 v.mapping_sha,v.`row_number`,v.metadata
FROM raw_data r JOIN raw_variables v ON v.id=r.variable_id;

CREATE OR REPLACE VIEW `sumo simulation` AS
SELECT s.id AS sample_id,s.run_id,s.simulated_ms,s.simulated_ms/3600000.0 AS time_h,
 CONVERT_TZ(s.acquired_at,'+00:00','__DISPLAY_TIMEZONE__') AS acquired_at,
 CONVERT_TZ(s.sensor_read_at,'+00:00','__DISPLAY_TIMEZONE__') AS sensor_read_at,
 s.acquired_at AS acquired_at_utc,s.sensor_read_at AS sensor_read_at_utc,
 LEFT(DATE_FORMAT(CONVERT_TZ(s.sensor_read_at,'+00:00','__DISPLAY_TIMEZONE__'),'%Y-%m-%d %H:%i:%s.%f'),23) AS plot_time,
 '__DISPLAY_TIMEZONE__' AS display_timezone,
 v.variable_name AS variable,v.unit,v.category,v.variable_type,v.model_sha,
 d.value_json,d.numeric_value,d.quality
FROM sumo_values d JOIN sumo_samples s ON s.id=d.sample_id
JOIN sumo_variables v ON v.id=d.variable_id;

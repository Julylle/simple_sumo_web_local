-- Create a dedicated database
CREATE DATABASE sumo_web_database
    CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;

-- Create the application account
CREATE USER 'sumo_web'@'localhost'
    IDENTIFIED BY 'sumo_web';

-- Grant access only to the application database
GRANT ALL PRIVILEGES ON sumo_timeseries.*
    TO 'sumo_web'@'localhost';
    
    
-- Confirm the server and administrative account
SELECT CURRENT_USER(), @@port;

-- Grant the application account access to its database
GRANT ALL PRIVILEGES ON sumo_web_database.*
    TO 'sumo_web'@'localhost';

-- Verify the assigned permissions
SHOW GRANTS FOR 'sumo_web'@'localhost';

-- Check whether the database exists on this server
SHOW DATABASES LIKE 'sumo_web_database';

-- Show the MySQL server's data directory
-- The database location is C:\ProgramData\MySQL\MySQL Server 8.1\Data\sumo_web_database
SHOW VARIABLES LIKE 'datadir';

-- Inspect the latest sensor readings
SELECT acquired_at, variable, OpcTag,
       raw_value, scaled_value, quality, error
FROM sumo_web_database.`raw data`
ORDER BY acquired_at DESC
LIMIT 30;

-- Check recent collection batches
SELECT batch_id, MAX(acquired_at) AS collected_at,
       COUNT(*) AS row_count,
       SUM(quality = 'good') AS good_count
FROM sumo_web_database.raw_data
WHERE acquired_at >= UTC_TIMESTAMP() - INTERVAL 10 MINUTE
GROUP BY batch_id
ORDER BY collected_at DESC;

-- Check the first and last time in the database
SELECT
    MIN(acquired_at) AS first_time,
    MAX(acquired_at) AS last_time
FROM sumo_web_database.`raw data`;

-- Check the first and last time in the database
SELECT
    MIN(acquired_at) AS first_time,
    MAX(acquired_at) AS last_time
FROM sumo_web_database.`sumo simulation`;


-- Find the latest simulation run
SELECT run_id, run_mode, started_at
FROM sumo_web_database.sumo_runs
ORDER BY started_at DESC
LIMIT 5;

-- Select the latest run
SET @run_id = (
    SELECT run_id
    FROM sumo_timeseries.sumo_runs
    ORDER BY started_at DESC
    LIMIT 1
);

-- Inspect its latest simulation values
SELECT time_h, sensor_read_at, variable, value_json, quality
FROM sumo_timeseries.`sumo simulation`
WHERE run_id = @run_id
ORDER BY simulated_ms DESC
LIMIT 30;

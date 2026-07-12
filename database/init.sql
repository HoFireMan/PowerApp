-- ==========================================
-- 1. 感測器 API 用電紀錄表 (原始)
-- ==========================================
CREATE TABLE IF NOT EXISTS power_consumption_records (
    id SERIAL PRIMARY KEY,
    branch_name VARCHAR(255) NOT NULL,
    device_name VARCHAR(255) NOT NULL,
    device_type VARCHAR(100),
    report_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    degree NUMERIC(10, 4),
    device_code_new VARCHAR(100),
    device_type_2_new VARCHAR(100),
    CONSTRAINT unique_record UNIQUE (branch_name, device_name, report_date, start_time)
);

CREATE INDEX IF NOT EXISTS idx_branch_name ON power_consumption_records(branch_name);
CREATE INDEX IF NOT EXISTS idx_report_date ON power_consumption_records(report_date);


-- ==========================================
-- 2. 台電帳單用電紀錄表 (成功數據)
-- ==========================================
CREATE TABLE IF NOT EXISTS taipower_billing_records (
    id SERIAL PRIMARY KEY,
    store_name VARCHAR(255) NOT NULL,       
    account_name VARCHAR(255),              
    account_number VARCHAR(100) NOT NULL,   
    billing_period VARCHAR(100),            
    billing_year INTEGER NOT NULL,          
    billing_month VARCHAR(20) NOT NULL,     
    usage_degree NUMERIC(15, 4),            
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_taipower_record UNIQUE (store_name, account_number, billing_year, billing_month)
);

CREATE INDEX IF NOT EXISTS idx_taipower_store ON taipower_billing_records(store_name);


-- ==========================================
-- 3. 台電帳單爬蟲錯誤日誌表 (失敗紀錄追蹤)
-- ==========================================
CREATE TABLE IF NOT EXISTS taipower_scraping_errors (
    id SERIAL PRIMARY KEY,
    store_name VARCHAR(255),                
    account_name VARCHAR(255),              
    account_number VARCHAR(100),            
    error_message TEXT,                     
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ==========================================
-- 4. 感測器 API 執行紀錄表 (API 抓取日誌)
-- ==========================================
CREATE TABLE IF NOT EXISTS sensor_api_execution_logs (
    id SERIAL PRIMARY KEY,
    target_start_date VARCHAR(20),          -- 目標擷取起始日期
    target_end_date VARCHAR(20),            -- 目標擷取結束日期
    total_stores_attempted INTEGER,         -- 預計抓取店家數
    successful_stores_count INTEGER,        -- 完全成功店家數
    failed_stores_list TEXT,                -- 發生錯誤的店家名單
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 程式執行時間
);

-- ==========================================
-- 💡 新增 5. 感測器數據品質檢測日誌表 (斷層與空缺紀錄)
-- ==========================================
CREATE TABLE IF NOT EXISTS sensor_data_quality_logs (
    id SERIAL PRIMARY KEY,
    check_start_date VARCHAR(20),           -- 檢測區間起點
    check_end_date VARCHAR(20),             -- 檢測區間終點
    expected_days INTEGER,                  -- 標準應有天數
    missing_stores_count INTEGER,           -- 完全無資料之店家數量
    gap_devices_count INTEGER,              -- 發生斷層之設備數量
    missing_stores_list TEXT,               -- 完全無資料之店家清單
    gap_devices_summary TEXT,               -- 斷層設備摘要說明
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 檢測執行時間
);
-- ==========================================
-- 1. 感測器 API 用電紀錄表 (原始)
-- ==========================================
CREATE TABLE IF NOT EXISTS power_consumption_records (
    id SERIAL PRIMARY KEY,
    branch_code VARCHAR(100),               -- 💡 新增：精準的店家代碼 (如 ant10)
    branch_name VARCHAR(255) NOT NULL,      -- 用於 Tableau 顯示的中文店名
    device_name VARCHAR(255) NOT NULL,
    device_type VARCHAR(100),
    report_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    degree NUMERIC(10, 4),
    device_code_new VARCHAR(100),
    device_type_2_new VARCHAR(100),
    device_mac VARCHAR(100),                -- 💡 新增：實體硬體 MAC 位址 (終極唯一碼)
    -- 💡 防呆限制升級：改用 branch_code 與 device_mac 作為終極基準 (徹底消滅幽靈設備)
    CONSTRAINT unique_record UNIQUE (branch_code, device_mac, report_date, start_time)
);

CREATE INDEX IF NOT EXISTS idx_branch_code ON power_consumption_records(branch_code);
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

-- ==========================================
-- 6. 感測器數據品質檢測 - 店家關聯映射表 (專供 Tableau 高速篩選)
-- ==========================================
CREATE TABLE IF NOT EXISTS sensor_data_quality_logs_mapping (
    id SERIAL PRIMARY KEY,
    log_id INTEGER,                         -- 對應到主表的 ID
    branch_code VARCHAR(100),               -- 店家代號 (如 ant14)
    branch_name VARCHAR(255),               -- 店家名稱
    issue_type VARCHAR(50),                 -- 異常類型 ('完全空缺' 或 '設備斷層')
    device_name VARCHAR(255),               -- 💡 新增：發生異常的設備名稱
    device_mac VARCHAR(100),                -- 💡 新增：硬體 MAC
    offline_days INTEGER                    -- 💡 新增：斷線天數
);

-- 建立索引，讓 Tableau 篩選速度飛快 ⚡
CREATE INDEX IF NOT EXISTS idx_mapping_log_id ON sensor_data_quality_logs_mapping(log_id);
CREATE INDEX IF NOT EXISTS idx_mapping_branch_code ON sensor_data_quality_logs_mapping(branch_code);
-- 建立用電數據資料表
CREATE TABLE IF NOT EXISTS power_consumption_records (
    id SERIAL PRIMARY KEY,
    branch_name VARCHAR(255) NOT NULL,       -- 店家 (對應 branchname)
    device_name VARCHAR(255) NOT NULL,       -- 設備名稱 (對應 devicename)
    device_type VARCHAR(100),                -- 設備類型 (對應 devicetypename)
    report_date DATE NOT NULL,               -- 日期 (對應 reportdate)
    start_time TIME NOT NULL,                -- 起始時間 (對應 starttm)
    end_time TIME NOT NULL,                  -- 結束時間 (對應 endtm)
    degree NUMERIC(10, 4),                   -- 用電度數 (對應 degree)
    device_code_new VARCHAR(100),            -- 設備編號 (經過 Python 萃取後)
    device_type_2_new VARCHAR(100),          -- 設備類型2 (經過 Python 萃取後)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- 系統寫入時間
    
    -- 【重要】加入唯一約束 (Unique Constraint)
    -- 這四個欄位的組合必須是唯一的。
    -- 當爬蟲抓到相同的店家、設備、日期和起始時間時，資料庫會視為重複，從而實現自動跳過的增量更新
    CONSTRAINT unique_record UNIQUE (branch_name, device_name, report_date, start_time)
);

-- 建立索引 (Index) 以加速未來你如果需要針對店家或日期拉取報表時的速度
CREATE INDEX idx_branch_name ON power_consumption_records(branch_name);
CREATE INDEX idx_report_date ON power_consumption_records(report_date);
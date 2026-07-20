// 檔案路徑: Energy Report Automation/data_checker.go
package main

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"os/exec"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/joho/godotenv"
	"github.com/lib/pq"
	_ "github.com/lib/pq"
	"github.com/xuri/excelize/v2"
)

// GapDevice 定義斷層設備的結構
type GapDevice struct {
	BranchID         string
	BranchName       string
	DeviceCode       string
	DeviceName       string
	FirstInstallDate string
	ExpectedDays     int
	ReportedDays     int
	MissingDays      int
	LastReportDate   string
	OfflineDays      int
	DeviceMac        string // 💡 依賴硬體 MAC 進行身分辨識
}

var dbPool *sql.DB

func initEnv() {
	ex, err := os.Executable()
	if err != nil {
		panic(err)
	}
	exPath := filepath.Dir(ex)
	if strings.Contains(exPath, "go-build") || strings.Contains(exPath, "Temp") {
		exPath, _ = os.Getwd()
	}
	envPath := filepath.Join(exPath, "..", ".env")
	godotenv.Load(envPath)
}

func getDBConnection() *sql.DB {
	host := os.Getenv("DB_HOST")
	if strings.ToLower(host) == "localhost" {
		host = "127.0.0.1"
	}
	port := os.Getenv("DB_PORT")
	user := os.Getenv("DB_USER")
	password := os.Getenv("DB_PASS")
	dbname := os.Getenv("DB_NAME")

	psqlInfo := fmt.Sprintf("host=%s port=%s user=%s password=%s dbname=%s sslmode=disable",
		host, port, user, password, dbname)

	db, err := sql.Open("postgres", psqlInfo)
	if err != nil {
		log.Fatalf("❌ 資料庫連線失敗: %v", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	return db
}

func saveCheckLogToDB(startStr, endStr string, expectedDays int, missingIds []string, gapDevices []GapDevice, missingListStr, gapSummaryStr string, storeDisplay map[string]string) {
	fmt.Printf("\n🐳 系統：準備將本次檢測報告同步寫入資料庫...\n")

	// 確保主表與關聯映射表都存在，並且包含設備明細的 3 個新欄位！
	createTableQuery := `
    CREATE TABLE IF NOT EXISTS sensor_data_quality_logs (
        id SERIAL PRIMARY KEY,
        check_start_date VARCHAR(20),
        check_end_date VARCHAR(20),
        expected_days INTEGER,
        missing_stores_count INTEGER,
        gap_devices_count INTEGER,
        missing_stores_list TEXT,
        gap_devices_summary TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
	CREATE TABLE IF NOT EXISTS sensor_data_quality_logs_mapping (
		id SERIAL PRIMARY KEY,
		log_id INTEGER,                         
		branch_code VARCHAR(100),               
		branch_name VARCHAR(255),               
		issue_type VARCHAR(50),
        device_name VARCHAR(255),
        device_mac VARCHAR(100),
        offline_days INTEGER
	);
	`
	dbPool.Exec(createTableQuery)

	// 1. 寫入主日誌表，並取得 log_id
	insertMainQuery := `
        INSERT INTO sensor_data_quality_logs (
            check_start_date, check_end_date, expected_days, 
            missing_stores_count, gap_devices_count, missing_stores_list, gap_devices_summary
        ) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id;
    `

	var logID int
	err := dbPool.QueryRow(insertMainQuery, startStr, endStr, expectedDays, len(missingIds), len(gapDevices), missingListStr, gapSummaryStr).Scan(&logID)

	if err != nil {
		fmt.Printf("    ❌ 檢測主報告寫入失敗: %v\n", err)
		return
	}

	// 2. 將出事的店家「與設備」逐筆寫入「映射表」供 Tableau 極速且獨立篩選
	insertMappingQuery := `
		INSERT INTO sensor_data_quality_logs_mapping (log_id, branch_code, branch_name, issue_type, device_name, device_mac, offline_days)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
	`
	mappingCount := 0

	// 處理完全空缺的店家 (因為沒有特定設備，明細留空)
	for _, mid := range missingIds {
		display := storeDisplay[mid]
		_, err := dbPool.Exec(insertMappingQuery, logID, mid, display, "完全空缺", "-", "-", expectedDays)
		if err == nil {
			mappingCount++
		}
	}

	// 處理設備斷層 (確保每台出事設備都獨立寫入一筆，不再打包！)
	for _, gd := range gapDevices {
		_, err := dbPool.Exec(insertMappingQuery, logID, gd.BranchID, gd.BranchName, "設備斷層", gd.DeviceName, gd.DeviceMac, gd.OfflineDays)
		if err == nil {
			mappingCount++
		}
	}

	fmt.Printf("    ✅ 檢測報告寫入成功！(主紀錄 1 筆，關聯映射 %d 筆)\n", mappingCount)
}

func performAutoFix(startStr, endStr string, missingBranches []string) {
	fmt.Println("\n========================================")
	fmt.Printf("🛠️ 啟動自動修復程序 (共需修復 %d 家店家)\n", len(missingBranches))
	fmt.Println("========================================")

	// 階段 1：嘗試透過 API 重新抓取
	fmt.Println("⏳ [階段 1] 正在向伺服器發送 API 請求嘗試補抓...")
	ex, _ := os.Executable()
	exPath := filepath.Dir(ex)
	if strings.Contains(exPath, "go-build") || strings.Contains(exPath, "Temp") {
		exPath, _ = os.Getwd()
	}
	apiFetcherExe := filepath.Join(exPath, "api_fetcher.exe")

	if _, err := os.Stat(apiFetcherExe); err == nil {
		branchesArg := strings.Join(missingBranches, ",")

		// 💡 終極防漏優化：3 天一包、5 核心慢速精準補抓，杜絕 API 假性成功漏資料！
		cmd := exec.Command(apiFetcherExe, startStr, endStr, "3", "5", branchesArg)

		cmd.Stdout = os.Stdout
		cmd.Stderr = os.Stderr
		err := cmd.Run()
		if err != nil {
			fmt.Printf("⚠️ 呼叫 api_fetcher 失敗: %v\n", err)
		} else {
			fmt.Println("✅ [階段 1 完成] API 精準補抓程序執行完畢。")
		}
	} else {
		fmt.Println("⚠️ 找不到 api_fetcher.exe，跳過 API 補抓階段。")
	}

	// 階段 2：針對空缺日子精準補零
	fmt.Println("\n⏳ [階段 2] 正在進行 SQL 交叉比對，針對絕對斷層補上 0 度紀錄...")

	fillZeroQuery := `
    WITH date_series AS (
        SELECT generate_series($1::date, $2::date - interval '1 day', '1 day')::date AS expected_date
    ),
    existing_devices AS (
        SELECT branch_code, device_mac, 
               MAX(device_code_new) as device_code_new, 
               MAX(branch_name) as branch_name, 
               MAX(device_name) as device_name, 
               MAX(device_type) as device_type, 
               MAX(device_type_2_new) as device_type_2_new,
               MIN(report_date) as first_install_date 
        FROM power_consumption_records 
        WHERE branch_code = ANY($3)
        GROUP BY branch_code, device_mac
    ),
    expected_records AS (
        SELECT d.expected_date, e.branch_code, e.branch_name, e.device_name, e.device_type, e.device_code_new, e.device_type_2_new, e.device_mac
        FROM date_series d CROSS JOIN existing_devices e
        WHERE d.expected_date >= e.first_install_date
    ),
    actual_records AS (
        SELECT DISTINCT report_date, branch_code, device_mac
        FROM power_consumption_records
        WHERE report_date >= $1 AND report_date < $2
        AND branch_code = ANY($3)
    )
    INSERT INTO power_consumption_records (
        branch_code, branch_name, device_name, device_type, report_date, start_time, end_time, degree, device_code_new, device_type_2_new, device_mac
    )
    SELECT 
        e.branch_code, e.branch_name, e.device_name, e.device_type, e.expected_date, 
        '00:00:00'::time, '23:59:59'::time, 0, e.device_code_new, e.device_type_2_new, e.device_mac
    FROM expected_records e
    LEFT JOIN actual_records a 
      ON e.expected_date = a.report_date 
     AND e.branch_code = a.branch_code 
     AND e.device_mac = a.device_mac
    WHERE a.report_date IS NULL
    ON CONFLICT (branch_code, device_mac, report_date, start_time) DO NOTHING;
    `

	res, err := dbPool.Exec(fillZeroQuery, startStr, endStr, pq.Array(missingBranches))
	if err != nil {
		fmt.Printf("❌ 執行補零程序時發生錯誤: %v\n", err)
	} else {
		rowsAffected, _ := res.RowsAffected()
		fmt.Printf("✅ [階段 2 完成] 成功為斷層設備精準補上 %d 筆 [0度] 紀錄！\n", rowsAffected)
		fmt.Println("💡 註：系統已啟動防呆過濾，設備「安裝前」的空白日將不予補零。")
	}
}

func main() {
	initEnv()
	dbPool = getDBConnection()
	defer dbPool.Close()

	startTotal := "ALL"
	endTotal := "ALL"
	autoFixFlag := "no_fix"

	if len(os.Args) >= 4 {
		startTotal = os.Args[1]
		endTotal = os.Args[2]
		autoFixFlag = os.Args[3]
	}

	fmt.Println("=== 啟動感測器數據空缺檢測 (即時健康監控版) ===")

	if startTotal == "ALL" {
		fmt.Println("🔍 啟動全時段掃描：正在計算資料庫最早期與最新紀錄...")
		var minDate, maxDate time.Time
		err := dbPool.QueryRow("SELECT MIN(report_date), MAX(report_date) FROM power_consumption_records").Scan(&minDate, &maxDate)
		if err == nil && !minDate.IsZero() && !maxDate.IsZero() {
			startTotal = minDate.Format("2006-01-02")
			endTotal = maxDate.AddDate(0, 0, 1).Format("2006-01-02")
		} else {
			log.Fatalf("❌ 資料庫目前無任何資料，無法執行全時段檢測。")
		}
	}

	startDt, _ := time.Parse("2006-01-02", startTotal)
	endDt, _ := time.Parse("2006-01-02", endTotal)
	expectedTotalDays := int(endDt.Sub(startDt).Hours() / 24)

	fmt.Printf("📅 檢測區間: %s 至 %s (查詢跨度: %d 天)\n\n", startTotal, endTotal, expectedTotalDays)

	ex, _ := os.Executable()
	exPath := filepath.Dir(ex)
	if strings.Contains(exPath, "go-build") || strings.Contains(exPath, "Temp") {
		exPath, _ = os.Getwd()
	}
	excelPath := filepath.Join(exPath, "店家ID.xlsx")

	f, err := excelize.OpenFile(excelPath)
	if err != nil {
		log.Fatalf("❌ 讀取 店家ID.xlsx 失敗: %v", err)
	}
	defer f.Close()

	rows, err := f.GetRows("店家資訊")
	if err != nil || len(rows) < 2 {
		log.Fatalf("❌ 讀取 Excel 失敗，找不到資料。")
	}

	headerRow := rows[0]
	idColIdx, nameColIdx := -1, -1
	for i, colCell := range headerRow {
		colStr := strings.TrimSpace(strings.ToLower(colCell))
		if colStr == "id" {
			idColIdx = i
		} else if colStr == "name" || colStr == "店名" || colStr == "店家名稱" || colStr == "公司名稱" {
			nameColIdx = i
		}
	}
	if nameColIdx == -1 {
		nameColIdx = idColIdx + 1
	}

	expectedIDs := make(map[string]bool)
	storeDisplay := make(map[string]string)

	for _, row := range rows[1:] {
		if len(row) <= idColIdx {
			continue
		}
		sid := strings.TrimSpace(row[idColIdx])
		if sid == "" || sid == "nan" {
			continue
		}

		sname := ""
		if len(row) > nameColIdx {
			sname = strings.TrimSpace(row[nameColIdx])
		}

		sidLower := strings.ToLower(sid)
		expectedIDs[sidLower] = true

		if sname != "" {
			storeDisplay[sid] = fmt.Sprintf("%s - %s", sid, sname)
		} else {
			storeDisplay[sid] = sid
		}
	}

	// 💡 終極進化：只承認「真正有耗電 (degree > 0)」的數據！無視所有假心跳。
	query := `
    WITH DeviceFirstSeen AS (
        SELECT branch_code, device_mac, MAX(device_code_new) as device_code_new, MAX(branch_name) as branch_name, MAX(device_name) as device_name, MIN(report_date) as first_install_date
        FROM power_consumption_records
		WHERE degree > 0
        GROUP BY branch_code, device_mac
    ),
    PeriodStats AS (
        SELECT branch_code, device_mac, 
               COUNT(DISTINCT report_date) as reported_days, 
               MAX(report_date) as last_report_date
        FROM power_consumption_records 
        WHERE report_date >= $1 AND report_date < $2
		  AND degree > 0
        GROUP BY branch_code, device_mac
    )
    SELECT d.branch_code, d.branch_name, d.device_code_new, d.device_name, 
           COALESCE(p.reported_days, 0) as reported_days, 
           COALESCE(p.last_report_date::text, '區間內無資料') as last_report_date, 
           d.first_install_date, d.device_mac
    FROM DeviceFirstSeen d
    LEFT JOIN PeriodStats p ON d.branch_code = p.branch_code AND d.device_mac = p.device_mac
    `

	fmt.Println("⏳ 正在比對數百萬筆資料，請稍候...")
	dbRows, err := dbPool.Query(query, startTotal, endTotal)
	if err != nil {
		log.Fatalf("❌ 資料庫查詢失敗: %v", err)
	}
	defer dbRows.Close()

	activeStores := make(map[string]bool)
	var allGapDevices []GapDevice

	for dbRows.Next() {
		var branchCode, branchName, deviceCode, deviceName, lastReport, deviceMac string
		var reportedDays int
		var firstInstall time.Time

		dbRows.Scan(&branchCode, &branchName, &deviceCode, &deviceName, &reportedDays, &lastReport, &firstInstall, &deviceMac)

		realIDLower := strings.ToLower(branchCode)

		if reportedDays > 0 {
			activeStores[realIDLower] = true
		}

		displayInfo := branchCode
		if name, ok := storeDisplay[branchCode]; ok {
			displayInfo = name
		}

		if len(lastReport) > 10 && lastReport != "區間內無資料" {
			lastReport = lastReport[:10]
		}
		firstInstallStr := firstInstall.Format("2006-01-02")

		tFirst, _ := time.Parse("2006-01-02", firstInstallStr)
		dynamicStart := startDt
		if tFirst.After(startDt) {
			dynamicStart = tFirst
		}

		expectedDays := int(endDt.Sub(dynamicStart).Hours() / 24)
		if expectedDays < 0 {
			expectedDays = 0
		}

		missingDays := expectedDays - reportedDays
		if missingDays < 0 {
			missingDays = 0
		}

		// 計算距離期末 (endDt) 斷線了幾天
		offlineDays := 0
		if lastReport == "區間內無資料" {
			offlineDays = expectedDays
		} else {
			tLast, _ := time.Parse("2006-01-02", lastReport)
			offlineDays = int(endDt.Sub(tLast).Hours() / 24)
			if offlineDays < 0 {
				offlineDays = 0
			}
		}

		gd := GapDevice{
			BranchID:         branchCode,
			BranchName:       displayInfo,
			DeviceCode:       deviceCode,
			DeviceName:       deviceName,
			FirstInstallDate: firstInstallStr,
			ExpectedDays:     expectedDays,
			ReportedDays:     reportedDays,
			MissingDays:      missingDays,
			LastReportDate:   lastReport,
			OfflineDays:      offlineDays,
			DeviceMac:        deviceMac,
		}

		// 🔑 只抓取「期末斷線超過 7 天」的異常設備
		if gd.OfflineDays > 7 {
			allGapDevices = append(allGapDevices, gd)
		}
	}

	var missingIds []string
	for expectedID := range expectedIDs {
		if !activeStores[expectedID] {
			for originalID := range storeDisplay {
				if strings.ToLower(originalID) == expectedID {
					missingIds = append(missingIds, originalID)
					break
				}
			}
		}
	}

	sort.Slice(allGapDevices, func(i, j int) bool {
		if allGapDevices[i].OfflineDays == allGapDevices[j].OfflineDays {
			return allGapDevices[i].BranchID < allGapDevices[j].BranchID
		}
		return allGapDevices[i].OfflineDays > allGapDevices[j].OfflineDays
	})

	sort.Strings(missingIds)

	timestamp := time.Now().Format("20060102_150405")
	reportFilename := fmt.Sprintf("數據空缺檢測報告_%s.xlsx", timestamp)
	reportDir := filepath.Join(exPath, "檢測報告")
	os.MkdirAll(reportDir, os.ModePerm)
	reportPath := filepath.Join(reportDir, reportFilename)

	outFile := excelize.NewFile()

	outFile.SetSheetName("Sheet1", "現正斷線設備清單")
	headers1 := []string{"店家ID", "店家資訊", "硬體MAC", "設備代碼", "設備名稱", "設備首次上線日", "應有天數", "實際有資料天數", "歷史缺漏天數", "最後收到資料日期", "❗距今斷線天數"}
	for i, h := range headers1 {
		colName, _ := excelize.ColumnNumberToName(i + 1)
		outFile.SetCellValue("現正斷線設備清單", colName+"1", h)
	}

	for i, gd := range allGapDevices {
		rowIdx := i + 2
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("A%d", rowIdx), gd.BranchID)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("B%d", rowIdx), gd.BranchName)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("C%d", rowIdx), gd.DeviceMac)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("D%d", rowIdx), gd.DeviceCode)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("E%d", rowIdx), gd.DeviceName)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("F%d", rowIdx), gd.FirstInstallDate)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("G%d", rowIdx), gd.ExpectedDays)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("H%d", rowIdx), gd.ReportedDays)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("I%d", rowIdx), gd.MissingDays)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("J%d", rowIdx), gd.LastReportDate)
		outFile.SetCellValue("現正斷線設備清單", fmt.Sprintf("K%d", rowIdx), gd.OfflineDays)
	}

	outFile.NewSheet("完全無數據店家")
	headers2 := []string{"店家ID", "店家資訊"}
	outFile.SetCellValue("完全無數據店家", "A1", headers2[0])
	outFile.SetCellValue("完全無數據店家", "B1", headers2[1])

	for i, mid := range missingIds {
		rowIdx := i + 2
		outFile.SetCellValue("完全無數據店家", fmt.Sprintf("A%d", rowIdx), mid)
		display := storeDisplay[mid]
		if display == "" {
			display = mid
		}
		outFile.SetCellValue("完全無數據店家", fmt.Sprintf("B%d", rowIdx), display)
	}

	if err := outFile.SaveAs(reportPath); err != nil {
		fmt.Printf("❌ 產出 Excel 報告時發生錯誤: %v\n", err)
	}

	fmt.Println("\n========================================")
	fmt.Println("🎉 數據空缺檢測完成！(期末健康監控版)")
	fmt.Printf("📊 發現 【%d】 家店完全無資料回傳。\n", len(missingIds))
	fmt.Printf("📊 發現 【%d】 個設備目前【斷線超過 7 天】。\n", len(allGapDevices))
	fmt.Println("========================================")

	missingListStr := "無"
	if len(missingIds) > 0 {
		var dList []string
		for _, mid := range missingIds {
			if d, ok := storeDisplay[mid]; ok {
				dList = append(dList, d)
			} else {
				dList = append(dList, mid)
			}
		}
		missingListStr = strings.Join(dList, ", ")
	}

	gapSummaryStr := "設備全數健康在線"
	if len(allGapDevices) > 0 {
		var gList []string
		limit := 20
		if len(allGapDevices) < 20 {
			limit = len(allGapDevices)
		}
		for i := 0; i < limit; i++ {
			gList = append(gList, fmt.Sprintf("%s-%s(已斷線%d天)", allGapDevices[i].BranchName, allGapDevices[i].DeviceName, allGapDevices[i].OfflineDays))
		}
		gapSummaryStr = strings.Join(gList, ", ")
		if len(allGapDevices) > 20 {
			gapSummaryStr += fmt.Sprintf(" ...等共 %d 項設備異常", len(allGapDevices))
		}
	}

	// 💡 呼叫更新版的方法：將 missingIds, gapDevices, storeDisplay 全數傳入以利建立 Tableau 映射表
	saveCheckLogToDB(startTotal, endTotal, expectedTotalDays, missingIds, allGapDevices, missingListStr, gapSummaryStr, storeDisplay)

	if autoFixFlag == "auto_fix" {
		var branchesToFetch []string
		branchesMap := make(map[string]bool)

		for _, mid := range missingIds {
			branchesMap[mid] = true
		}
		for _, gd := range allGapDevices {
			branchesMap[gd.BranchID] = true
		}

		for b := range branchesMap {
			branchesToFetch = append(branchesToFetch, b)
		}

		if len(branchesToFetch) > 0 {
			performAutoFix(startTotal, endTotal, branchesToFetch)
		} else {
			fmt.Println("\n✅ 檢測結果完美，全數設備健康在線，無需啟動自動修復與補零！")
		}
	}
}

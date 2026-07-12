// 檔案路徑: Energy Report Automation/data_checker.go
package main

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/joho/godotenv"
	_ "github.com/lib/pq"
	"github.com/xuri/excelize/v2"
)

var (
	dbPool *sql.DB
)

type GapDevice struct {
	BranchID       string
	BranchName     string
	DeviceName     string
	ExpectedDays   int
	ReportedDays   int
	MissingDays    int
	LastReportDate string
}

func initEnv() {
	ex, _ := os.Executable()
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
	return db
}

func readStoreInfo(filePath string) (map[string]string, error) {
	f, err := excelize.OpenFile(filePath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	rows, err := f.GetRows("店家資訊")
	if err != nil {
		return nil, err
	}

	if len(rows) == 0 {
		return nil, fmt.Errorf("找不到資料")
	}

	idIdx, nameIdx := -1, -1
	for i, col := range rows[0] {
		lowerCol := strings.ToLower(strings.TrimSpace(col))
		if lowerCol == "id" {
			idIdx = i
		} else if strings.Contains(lowerCol, "name") || strings.Contains(lowerCol, "名") {
			nameIdx = i
		}
	}

	if idIdx == -1 {
		return nil, fmt.Errorf("找不到 ID 欄位")
	}
	if nameIdx == -1 {
		nameIdx = idIdx + 1 // 猜測下一個是店名
	}

	storeMap := make(map[string]string)
	for _, row := range rows[1:] {
		if len(row) > idIdx {
			id := strings.TrimSpace(row[idIdx])
			if id != "" && id != "nan" {
				name := ""
				if len(row) > nameIdx {
					name = strings.TrimSpace(row[nameIdx])
				}
				storeMap[id] = name
			}
		}
	}
	return storeMap, nil
}

func saveCheckLogToDB(startStr, endStr string, expectedDays int, missingIds []string, gapDevices []GapDevice, storeMap map[string]string) {
	var missingStrs []string
	for _, id := range missingIds {
		if name, ok := storeMap[id]; ok && name != "" {
			missingStrs = append(missingStrs, fmt.Sprintf("%s-%s", id, name))
		} else {
			missingStrs = append(missingStrs, id)
		}
	}
	missingList := "無"
	if len(missingStrs) > 0 {
		missingList = strings.Join(missingStrs, ", ")
	}

	var gapSummaryStrs []string
	limit := len(gapDevices)
	if limit > 20 {
		limit = 20
	}
	for i := 0; i < limit; i++ {
		gd := gapDevices[i]
		gapSummaryStrs = append(gapSummaryStrs, fmt.Sprintf("%s-%s(缺%d天)", gd.BranchName, gd.DeviceName, gd.MissingDays))
	}
	gapSummary := "資料完整無斷層"
	if len(gapSummaryStrs) > 0 {
		gapSummary = strings.Join(gapSummaryStrs, ", ")
		if len(gapDevices) > 20 {
			gapSummary += fmt.Sprintf(" ...等共 %d 項設備異常", len(gapDevices))
		}
	}

	query := `
		INSERT INTO sensor_data_quality_logs (
			check_start_date, check_end_date, expected_days, 
			missing_stores_count, gap_devices_count, missing_stores_list, gap_devices_summary
		) VALUES ($1, $2, $3, $4, $5, $6, $7);
	`
	_, err := dbPool.Exec(query, startStr, endStr, expectedDays, len(missingIds), len(gapDevices), missingList, gapSummary)
	if err != nil {
		fmt.Printf("\n    ❌ 檢測報告寫入資料庫失敗: %v\n", err)
	} else {
		fmt.Println("\n    ✅ 檢測報告同步寫入資料庫成功！")
	}
}

func performAutoFixZeroFill(startStr, endStr string, branchesToFix []string, storeMap map[string]string) {
	fmt.Println("\n========================================")
	fmt.Printf("🛠️ 啟動自動修復：SQL 交叉比對精準補 0 (共 %d 家店家)\n", len(branchesToFix))
	fmt.Println("========================================")

	var searchNames []string
	for _, id := range branchesToFix {
		searchNames = append(searchNames, id)
		if name, ok := storeMap[id]; ok && name != "" {
			searchNames = append(searchNames, name)
		}
	}

	// 將 string slice 轉成 PostgreSQL 陣列格式字串
	pgArrayStr := "{" + strings.Join(searchNames, ",") + "}"

	fillZeroQuery := `
        WITH date_series AS (
            SELECT generate_series($1::date, $2::date - interval '1 day', '1 day')::date AS expected_date
        ),
        existing_devices AS (
            SELECT DISTINCT branch_name, device_name, device_type, device_code_new, device_type_2_new 
            FROM power_consumption_records 
            WHERE branch_name = ANY($3::varchar[])
        ),
        expected_records AS (
            SELECT d.expected_date, e.branch_name, e.device_name, e.device_type, e.device_code_new, e.device_type_2_new
            FROM date_series d CROSS JOIN existing_devices e
        ),
        actual_records AS (
            SELECT DISTINCT report_date, branch_name, device_name
            FROM power_consumption_records
            WHERE report_date >= $1 AND report_date < $2
            AND branch_name = ANY($3::varchar[])
        )
        INSERT INTO power_consumption_records (
            branch_name, device_name, device_type, report_date, start_time, end_time, degree, device_code_new, device_type_2_new
        )
        SELECT 
            e.branch_name, e.device_name, e.device_type, e.expected_date, 
            '00:00:00'::time, '23:59:59'::time, 0, e.device_code_new, e.device_type_2_new
        FROM expected_records e
        LEFT JOIN actual_records a 
          ON e.expected_date = a.report_date 
         AND e.branch_name = a.branch_name 
         AND e.device_name = a.device_name
        WHERE a.report_date IS NULL
        ON CONFLICT (branch_name, device_name, report_date, start_time) DO NOTHING;
	`

	res, err := dbPool.Exec(fillZeroQuery, startStr, endStr, pgArrayStr)
	if err != nil {
		fmt.Printf("❌ 執行補零程序時發生錯誤: %v\n", err)
		return
	}

	rowsAffected, _ := res.RowsAffected()
	fmt.Printf("✅ [階段完成] 成功為斷層設備精準補上 %d 筆 [0度] 紀錄！\n", rowsAffected)
}

func main() {
	initEnv()
	dbPool = getDBConnection()
	defer dbPool.Close()

	var startTotal, endTotal, autoFix string
	if len(os.Args) >= 4 {
		startTotal = os.Args[1]
		endTotal = os.Args[2]
		autoFix = os.Args[3]
	} else {
		startTotal = "ALL"
		endTotal = "ALL"
		autoFix = "no_fix"
	}

	fmt.Println("=== 啟動感測器數據空缺檢測 ===")

	if startTotal == "ALL" {
		fmt.Println("🔍 啟動全時段掃描：正在計算資料庫最早期與最新紀錄...")
		var minDate, maxDate string
		err := dbPool.QueryRow("SELECT MIN(report_date)::text, MAX(report_date)::text FROM power_consumption_records").Scan(&minDate, &maxDate)
		if err != nil || minDate == "" {
			log.Fatalf("❌ 資料庫目前無任何資料，無法執行全時段檢測。")
		}
		
		tMin, _ := time.Parse("2006-01-02", minDate[:10])
		tMax, _ := time.Parse("2006-01-02", maxDate[:10])
		
		startTotal = tMin.Format("2006-01-02")
		endTotal = tMax.AddDate(0, 0, 1).Format("2006-01-02") // 包含尾日
	}

	layout := "2006-01-02"
	startDt, _ := time.Parse(layout, startTotal)
	endDt, _ := time.Parse(layout, endTotal)
	expectedDays := int(endDt.Sub(startDt).Hours() / 24)

	fmt.Printf("📅 檢測區間: %s 至 %s (應有天數: %d 天)\n\n", startTotal, endTotal, expectedDays)

	// 讀取 Excel 店家 ID
	exPath, _ := os.Getwd()
	if strings.Contains(exPath, "go-build") || strings.Contains(exPath, "Temp") {
		exPath = filepath.Dir(os.Args[0])
	}
	excelPath := filepath.Join(exPath, "店家ID.xlsx")
	storeMap, err := readStoreInfo(excelPath)
	if err != nil {
		log.Fatalf("❌ 讀取 店家ID.xlsx 失敗: %v", err)
	}
	
	// 建立反向對照表 Name -> ID
	nameToID := make(map[string]string)
	for id, name := range storeMap {
		if name != "" {
			nameToID[name] = id
		}
		nameToID[id] = id // 確保 ID 也能查到 ID
	}

	// 查詢資料庫
	fmt.Println("⏳ 正在比對數百萬筆資料，請稍候...")
	query := `
		SELECT branch_name, device_name, COUNT(DISTINCT report_date) as reported_days, MAX(report_date)::text as last_report_date
		FROM power_consumption_records 
		WHERE report_date >= $1 AND report_date < $2
		GROUP BY branch_name, device_name
	`
	rows, err := dbPool.Query(query, startTotal, endTotal)
	if err != nil {
		log.Fatalf("❌ 資料庫查詢失敗: %v", err)
	}
	defer rows.Close()

	actualIDs := make(map[string]bool)
	var gapDevices []GapDevice

	for rows.Next() {
		var branchName, deviceName, lastReport string
		var reportedDays int
		rows.Scan(&branchName, &deviceName, &reportedDays, &lastReport)

		// 嘗試將中文店名還原為 ID
		realID := branchName
		if mappedID, exists := nameToID[branchName]; exists {
			realID = mappedID
		}

		actualIDs[realID] = true
		missingDays := expectedDays - reportedDays

		if missingDays > 0 {
			displayInfo := realID
			if name, ok := storeMap[realID]; ok && name != "" {
				displayInfo = fmt.Sprintf("%s - %s", realID, name)
			}
			
			gapDevices = append(gapDevices, GapDevice{
				BranchID:       realID,
				BranchName:     displayInfo,
				DeviceName:     deviceName,
				ExpectedDays:   expectedDays,
				ReportedDays:   reportedDays,
				MissingDays:    missingDays,
				LastReportDate: lastReport[:10],
			})
		}
	}

	// 找出完全消失的 ID
	var missingIds []string
	for expectedID := range storeMap {
		if !actualIDs[expectedID] {
			missingIds = append(missingIds, expectedID)
		}
	}

	// 排序斷層設備 (缺漏天數降序)
	sort.Slice(gapDevices, func(i, j int) bool {
		if gapDevices[i].MissingDays == gapDevices[j].MissingDays {
			return gapDevices[i].BranchID < gapDevices[j].BranchID
		}
		return gapDevices[i].MissingDays > gapDevices[j].MissingDays
	})

	saveCheckLogToDB(startTotal, endTotal, expectedDays, missingIds, gapDevices, storeMap)

	// --- 產出 Excel ---
	f := excelize.NewFile()
	
	// Sheet 1: 設備資料斷層
	sheet1 := "設備資料斷層"
	f.SetSheetName("Sheet1", sheet1)
	if len(gapDevices) > 0 {
		headers := []string{"店家ID", "店家資訊", "設備名稱", "應有天數", "實際有資料天數", "缺漏天數", "最後收到資料日期"}
		for i, h := range headers {
			cell, _ := excelize.CoordinatesToCellName(i+1, 1)
			f.SetCellValue(sheet1, cell, h)
		}
		for r, gd := range gapDevices {
			f.SetCellValue(sheet1, fmt.Sprintf("A%d", r+2), gd.BranchID)
			f.SetCellValue(sheet1, fmt.Sprintf("B%d", r+2), gd.BranchName)
			f.SetCellValue(sheet1, fmt.Sprintf("C%d", r+2), gd.DeviceName)
			f.SetCellValue(sheet1, fmt.Sprintf("D%d", r+2), gd.ExpectedDays)
			f.SetCellValue(sheet1, fmt.Sprintf("E%d", r+2), gd.ReportedDays)
			f.SetCellValue(sheet1, fmt.Sprintf("F%d", r+2), gd.MissingDays)
			f.SetCellValue(sheet1, fmt.Sprintf("G%d", r+2), gd.LastReportDate)
		}
	} else {
		f.SetCellValue(sheet1, "A1", "該期間內所有上線設備資料皆完整")
	}

	// Sheet 2: 完全無數據店家
	sheet2 := "完全無數據店家"
	f.NewSheet(sheet2)
	if len(missingIds) > 0 {
		f.SetCellValue(sheet2, "A1", "店家ID")
		f.SetCellValue(sheet2, "B1", "店家資訊")
		for r, mid := range missingIds {
			f.SetCellValue(sheet2, fmt.Sprintf("A%d", r+2), mid)
			info := mid
			if name, ok := storeMap[mid]; ok && name != "" {
				info = fmt.Sprintf("%s - %s", mid, name)
			}
			f.SetCellValue(sheet2, fmt.Sprintf("B%d", r+2), info)
		}
	} else {
		f.SetCellValue(sheet2, "A1", "所有店家皆有資料")
	}

	timestamp := time.Now().Format("20060102_150405")
	reportName := fmt.Sprintf("數據空缺檢測報告_%s.xlsx", timestamp)

	// 💡 新增：自動建立專屬的「檢測報告」資料夾
	reportDir := filepath.Join(exPath, "檢測報告")
	if err := os.MkdirAll(reportDir, os.ModePerm); err != nil {
		fmt.Printf("❌ 無法建立檢測報告資料夾: %v\n", err)
	}

	// 組合完整的儲存路徑
	reportPath := filepath.Join(reportDir, reportName)

	if err := f.SaveAs(reportPath); err != nil {
		fmt.Printf("❌ 儲存 Excel 失敗: %v\n", err)
	}

	fmt.Println("\n========================================")
	fmt.Println("🎉 數據空缺檢測完成！")
	fmt.Printf("📊 發現 【%d】 家店完全無資料回傳。\n", len(missingIds))
	fmt.Printf("📊 發現 【%d】 個設備發生資料斷層/缺漏。\n", len(gapDevices))
	fmt.Printf("📁 詳細報告已收納至: %s\n", reportPath)
	fmt.Println("========================================")

	// 自動修復機制
	if autoFix == "auto_fix" {
		fixSet := make(map[string]bool)
		for _, mid := range missingIds {
			fixSet[mid] = true
		}
		for _, gd := range gapDevices {
			fixSet[gd.BranchID] = true
		}
		
		var fixList []string
		for id := range fixSet {
			fixList = append(fixList, id)
		}

		if len(fixList) > 0 {
			performAutoFixZeroFill(startTotal, endTotal, fixList, storeMap)
		} else {
			fmt.Println("\n✅ 檢測結果完美，無需啟動自動修復與補零！")
		}
	}
}
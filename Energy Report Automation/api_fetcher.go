// 檔案路徑: Energy Report Automation/api_fetcher.go
package main

import (
	"bufio"
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/joho/godotenv"
	_ "github.com/lib/pq"
	"github.com/xuri/excelize/v2"
)

// --- 結構體定義 ---

type APIRequestHeader struct {
	Datetime   string `json:"datetime"`
	Txcode     string `json:"txcode"`
	Appversion string `json:"appversion"`
	Usercode   string `json:"usercode"`
	Token      string `json:"token"`
}

type APIRequestMessage struct {
	Startdate      string   `json:"startdate"`
	Enddate        string   `json:"enddate"`
	Branchcode     string   `json:"branchcode"`
	Devicecodelist []string `json:"devicecodelist"`
}

type APIRequest struct {
	Header  APIRequestHeader  `json:"header"`
	Message APIRequestMessage `json:"message"`
}

type SensorData struct {
	BranchName     string  `json:"branchname"`
	DeviceName     string  `json:"devicename"`
	DeviceTypeName string  `json:"devicetypename"`
	ReportDate     string  `json:"reportdate"`
	StartTm        string  `json:"starttm"`
	EndTm          string  `json:"endtm"`
	Degree         float64 `json:"degree"`
}

type APIResponse struct {
	Message struct {
		Data []SensorData `json:"data"`
	} `json:"message"`
}

type DBRecord struct {
	BranchName     string
	DeviceName     string
	DeviceType     string
	ReportDate     string
	StartTime      string
	EndTime        string
	Degree         float64
	DeviceCodeNew  string
	DeviceType2New string
}

// --- 全域常數與變數 ---
var (
	httpClient = &http.Client{Timeout: 60 * time.Second}
	apiUrl     string
	dbPool     *sql.DB
	mutex      sync.Mutex

	totalProcessed int
	failedBranches = make(map[string]bool)

	furnitureKeywords = []string{
		"電燈", "冰箱", "冷氣", "冷凍櫃", "微波爐", "烤箱",
		"電鍋", "氣炸鍋", "洗碗機", "咖啡機", "飲水機", "電風扇", "總電源",
		"除濕機", "空氣清淨機", "洗衣機", "烘衣機", "電視", "投影機",
		"插座", "電腦", "伺服器", "監視器", "吹風機", "熱水器", "抽風機",
	}
)

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

	apiUrl = os.Getenv("API_URL")
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

	db.SetMaxOpenConns(20)
	db.SetMaxIdleConns(10)
	db.SetConnMaxLifetime(5 * time.Minute)

	return db
}

// 輔助功能
func extractDeviceCode(deviceName string) string {
	re := regexp.MustCompile(`[A-Za-z0-9]+`)
	match := re.FindString(deviceName)
	return match
}

func extractFurnitureType(deviceName, deviceTypeName string) string {
	for _, kw := range furnitureKeywords {
		if strings.Contains(deviceName, kw) {
			return kw
		}
	}
	if strings.Contains(deviceTypeName, "其他") {
		parts := strings.SplitN(deviceName, " ", 2)
		if len(parts) > 1 {
			return parts[1]
		}
		return deviceName
	}
	return deviceTypeName
}

func getDateSegments(startStr, endStr string, step int) [][2]string {
	layout := "2006-01-02"
	start, _ := time.Parse(layout, startStr)
	end, _ := time.Parse(layout, endStr)
	var segments [][2]string

	curr := start
	for curr.Before(end) {
		segEnd := curr.AddDate(0, 0, step)
		if segEnd.After(end) {
			segEnd = end
		}
		segments = append(segments, [2]string{
			curr.Format(layout) + " 00:00",
			segEnd.Format(layout) + " 00:00",
		})
		curr = segEnd
	}
	return segments
}

// 批次寫入資料庫
func processAndInsertData(rawData []SensorData, branchCode string) (int, error) {
	if len(rawData) == 0 {
		return 0, nil
	}

	var records []DBRecord
	for _, raw := range rawData {
		devName := strings.TrimSpace(raw.DeviceName)
		if devName == "" {
			continue
		}

		bName := raw.BranchName
		if bName == "" {
			bName = branchCode
		}

		dateOnly := strings.Split(raw.ReportDate, "T")[0]

		record := DBRecord{
			BranchName:     bName,
			DeviceName:     devName,
			DeviceType:     raw.DeviceTypeName,
			ReportDate:     dateOnly,
			StartTime:      raw.StartTm,
			EndTime:        raw.EndTm,
			Degree:         raw.Degree,
			DeviceCodeNew:  extractDeviceCode(devName),
			DeviceType2New: extractFurnitureType(devName, raw.DeviceTypeName),
		}
		records = append(records, record)
	}

	if len(records) == 0 {
		return 0, nil
	}

	valueStrings := make([]string, 0, len(records))
	valueArgs := make([]interface{}, 0, len(records)*9)

	i := 1
	for _, rec := range records {
		valueStrings = append(valueStrings, fmt.Sprintf("($%d, $%d, $%d, $%d, $%d, $%d, $%d, $%d, $%d)",
			i, i+1, i+2, i+3, i+4, i+5, i+6, i+7, i+8))
		valueArgs = append(valueArgs, rec.BranchName, rec.DeviceName, rec.DeviceType,
			rec.ReportDate, rec.StartTime, rec.EndTime, rec.Degree, rec.DeviceCodeNew, rec.DeviceType2New)
		i += 9
	}

	query := fmt.Sprintf(`
		INSERT INTO power_consumption_records (
			branch_name, device_name, device_type, report_date, 
			start_time, end_time, degree, device_code_new, device_type_2_new
		) VALUES %s
		ON CONFLICT (branch_name, device_name, report_date, start_time) DO NOTHING;
	`, strings.Join(valueStrings, ","))

	_, err := dbPool.Exec(query, valueArgs...)
	if err != nil {
		return 0, fmt.Errorf("DB Batch Insert Error: %v", err)
	}

	return len(records), nil
}

// 遞迴降級重試抓取函數
func fetchSegmentWithFallback(branchCode, startStr, endStr string, step int) (int, bool) {
	reqBody := APIRequest{
		Header: APIRequestHeader{
			Datetime:   time.Now().Format("2006-01-02T15:04:05+08:00"),
			Txcode:     "BASIC_REPORT_CREATE",
			Appversion: "2023082401",
			Usercode:   "antnex",
			Token:      "",
		},
		Message: APIRequestMessage{
			Startdate:      startStr,
			Enddate:        endStr,
			Branchcode:     branchCode,
			Devicecodelist: []string{},
		},
	}

	jsonValue, _ := json.Marshal(reqBody)
	req, _ := http.NewRequest("POST", apiUrl, bytes.NewBuffer(jsonValue))
	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient.Do(req)
	var processedCount int

	if err == nil {
		defer resp.Body.Close()
		if resp.StatusCode == 200 {
			body, _ := io.ReadAll(resp.Body)
			var apiResp APIResponse
			if err := json.Unmarshal(body, &apiResp); err == nil {
				if len(apiResp.Message.Data) > 0 {
					processedCount, err = processAndInsertData(apiResp.Message.Data, branchCode)
					if err != nil {
						fmt.Printf("  [錯誤] 寫入資料庫失敗: %v\n", err)
					}
				}
				return processedCount, false
			} else {
				err = fmt.Errorf("JSON 解析錯誤")
			}
		} else {
			err = fmt.Errorf("HTTP %d", resp.StatusCode)
		}
	}

	fallbackStep := step
	if step > 30 {
		fallbackStep = 30
		fmt.Printf("  [重試] 店家 %s 時段 %s~%s 發生錯誤，改為 %d 天重試...\n", branchCode, startStr, endStr, fallbackStep)
	} else if step > 7 {
		fallbackStep = 7
		fmt.Printf("  [重試] 店家 %s 時段 %s~%s 發生錯誤，改為 %d 天重試...\n", branchCode, startStr, endStr, fallbackStep)
	} else {
		fmt.Printf("  [放棄] 店家 %s 時段 %s~%s 已達最小重試天數仍失敗: %v\n", branchCode, startStr, endStr, err)
		return 0, true
	}

	subSegments := getDateSegments(strings.Split(startStr, " ")[0], strings.Split(endStr, " ")[0], fallbackStep)
	totalFallbackProcessed := 0
	hasFatalError := false

	for _, sub := range subSegments {
		cnt, isErr := fetchSegmentWithFallback(branchCode, sub[0], sub[1], fallbackStep)
		totalFallbackProcessed += cnt
		if isErr {
			hasFatalError = true
		}
	}
	return totalFallbackProcessed, hasFatalError
}

func readExcelStores(filePath string) ([]string, error) {
	f, err := excelize.OpenFile(filePath)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	cols, err := f.GetCols("店家資訊")
	if err != nil {
		return nil, err
	}

	var storeCodes []string
	idIndex := -1

	for i, col := range cols {
		if len(col) > 0 && col[0] == "ID" {
			idIndex = i
			break
		}
	}

	if idIndex == -1 {
		return nil, fmt.Errorf("找不到 [ID] 欄位")
	}

	for _, rowValue := range cols[idIndex][1:] {
		v := strings.TrimSpace(rowValue)
		if v != "" && v != "nan" {
			storeCodes = append(storeCodes, v)
		}
	}
	return storeCodes, nil
}

func saveApiExecutionLog(startStr, endStr string, totalStores, successCount int, failedStr string) {
	query := `
		INSERT INTO sensor_api_execution_logs (
			target_start_date, target_end_date, total_stores_attempted, 
			successful_stores_count, failed_stores_list
		) VALUES ($1, $2, $3, $4, $5);
	`
	_, err := dbPool.Exec(query, startStr, endStr, totalStores, successCount, failedStr)
	if err != nil {
		fmt.Printf("\n    ❌ 執行紀錄寫入資料庫失敗: %v\n", err)
	} else {
		fmt.Println("\n    ✅ 執行紀錄寫入成功！")
	}
}

func main() {
	initEnv()
	dbPool = getDBConnection()
	defer dbPool.Close()

	var startTotal, endTotal string
	var stepDays, maxWorkers int
	var targetBranchesArg string

	if len(os.Args) >= 5 {
		startTotal = os.Args[1]
		endTotal = os.Args[2]
		stepDays, _ = strconv.Atoi(os.Args[3])
		maxWorkers, _ = strconv.Atoi(os.Args[4])

		// 💡 解析第五個參數：特定店家名單
		if len(os.Args) >= 6 {
			targetBranchesArg = os.Args[5]
		} else {
			targetBranchesArg = "ALL"
		}
	} else {
		// 開發時直接測試的防呆提示
		reader := bufio.NewReader(os.Stdin)
		fmt.Print("請輸入起始日期 (YYYY-MM-DD) [預設: 2020-05-20]: ")
		inStart, _ := reader.ReadString('\n')
		inStart = strings.TrimSpace(inStart)
		if inStart == "" {
			startTotal = "2020-05-20"
		} else {
			startTotal = inStart
		}

		fmt.Print("請輸入結束日期 (YYYY-MM-DD) [預設: 2026-06-01]: ")
		inEnd, _ := reader.ReadString('\n')
		inEnd = strings.TrimSpace(inEnd)
		if inEnd == "" {
			endTotal = "2026-06-01"
		} else {
			endTotal = inEnd
		}

		stepDays = 30
		maxWorkers = 10
		targetBranchesArg = "ALL"
	}

	startTimeExec := time.Now()

	// 💡 智能判斷模式：指定店家 vs 讀取全部 Excel
	var targetBranches []string
	if targetBranchesArg != "ALL" && targetBranchesArg != "" {
		parts := strings.Split(targetBranchesArg, ",")
		for _, p := range parts {
			if strings.TrimSpace(p) != "" {
				targetBranches = append(targetBranches, strings.TrimSpace(p))
			}
		}
		fmt.Printf("\n=== 🎯 啟動 [指定店家] 補抓模式 (Golang 版) ===\n")
		fmt.Printf("目標店家: %s\n", strings.Join(targetBranches, ", "))
	} else {
		fmt.Printf("\n=== 🚀 啟動 [全自動多執行緒] 模式 (Golang 版) ===\n")
		exPath, _ := os.Getwd()
		if strings.Contains(exPath, "go-build") || strings.Contains(exPath, "Temp") {
			exPath = filepath.Dir(os.Args[0])
		}
		excelPath := filepath.Join(exPath, "店家ID.xlsx")

		var err error
		targetBranches, err = readExcelStores(excelPath)
		if err != nil {
			log.Fatalf("❌ 讀取 Excel 失敗: %v", err)
		}
	}

	fmt.Printf("📅 擷取區間: %s 至 %s\n", startTotal, endTotal)
	fmt.Printf("⏳ 間隔天數: %d 天\n", stepDays)

	segments := getDateSegments(startTotal, endTotal, stepDays)
	type Task struct {
		Branch string
		Start  string
		End    string
	}

	var tasks []Task
	for _, branch := range targetBranches {
		for _, seg := range segments {
			tasks = append(tasks, Task{Branch: branch, Start: seg[0], End: seg[1]})
		}
	}
	fmt.Printf("總共為 %d 家店切分出 %d 個抓取任務。\n", len(targetBranches), len(tasks))

	taskChan := make(chan Task, len(tasks))
	var wg sync.WaitGroup
	totalTasks := len(tasks)
	var completedTasks int

	for i := 0; i < maxWorkers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for t := range taskChan {
				processed, isErr := fetchSegmentWithFallback(t.Branch, t.Start, t.End, stepDays)

				mutex.Lock()
				totalProcessed += processed
				if isErr {
					failedBranches[t.Branch] = true
				}

				// 💡 進度條繪製邏輯
				completedTasks++
				percent := float64(completedTasks) / float64(totalTasks) * 100
				barLength := 30
				filled := int(float64(barLength) * float64(completedTasks) / float64(totalTasks))
				if filled > barLength {
					filled = barLength
				}
				// 產生動態長度的 █ 方塊
				bar := strings.Repeat("█", filled) + strings.Repeat(" ", barLength-filled)
				elapsed := time.Since(startTimeExec).Truncate(time.Second)

				// 輸出給 UI 的特殊格式 (UI 會攔截這個格式做單行原地覆蓋)
				fmt.Printf("總進度: %3.0f%%|%s| %d/%d [耗時: %s]\n", percent, bar, completedTasks, totalTasks, elapsed)

				mutex.Unlock()
			}
		}()
	}

	for _, t := range tasks {
		taskChan <- t
	}
	close(taskChan)

	wg.Wait()

	totalStores := len(targetBranches)
	failedCount := len(failedBranches)
	successCount := totalStores - failedCount

	var failedList []string
	for k := range failedBranches {
		failedList = append(failedList, k)
	}
	failedStr := "無"
	if len(failedList) > 0 {
		failedStr = strings.Join(failedList, ", ")
	}

	saveApiExecutionLog(startTotal, endTotal, totalStores, successCount, failedStr)

	fmt.Println("\n==============================")
	fmt.Println("🎉 擷取與寫入程序結束！")
	fmt.Printf("共嘗試寫入 %d 筆資料。\n", totalProcessed)
	fmt.Printf("成功店家: %d 家 | 失敗店家: %d 家\n", successCount, failedCount)
	fmt.Printf("總耗時: %.2f 秒\n", time.Since(startTimeExec).Seconds())
	fmt.Println("==============================")
}

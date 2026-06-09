package main

import (
	"bufio"
	"log"
	"os"
	"path/filepath"
	"strings"

	"agenthub/gateway/internal/app"
	"agenthub/gateway/internal/httpapi"
)

// loadDotenv 从 repo 根目录读取 .env 文件，将未设置的环境变量注入进程。
func loadDotenv(repoRoot string) {
	path := filepath.Join(repoRoot, ".env")
	f, err := os.Open(path)
	if err != nil {
		return // .env 文件不存在时静默跳过
	}
	defer f.Close()

	scanner := bufio.NewScanner(f)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		// 支持 KEY=value 和 KEY="value"
		eq := strings.Index(line, "=")
		if eq < 0 {
			continue
		}
		key := strings.TrimSpace(line[:eq])
		val := strings.TrimSpace(line[eq+1:])
		// 去掉引号
		val = strings.Trim(val, `"'`)
		// 只在环境变量未设时注入（已设的环境变量优先级更高）
		if os.Getenv(key) == "" {
			os.Setenv(key, val)
		}
	}
}

// main 启动 Gin Gateway，并通过环境变量指向 Runtime FastAPI 内部服务。
func main() {
	repoRoot, err := os.Getwd()
	if err != nil {
		log.Fatalf("resolve repo root: %v", err)
	}

	// 尝试从 repo 根目录加载 .env（开发体验：不需要手动 export）
	loadDotenv(repoRoot)
	// 也尝试父目录（如果从 gateway/ 目录启动）
	loadDotenv(filepath.Join(repoRoot, ".."))

	gatewayApp, demoToken, err := app.New(repoRoot)
	if err != nil {
		log.Fatalf("bootstrap gateway app: %v", err)
	}
	router := httpapi.NewRouter(gatewayApp)

	port := os.Getenv("GATEWAY_PORT")
	if port == "" {
		port = "8080"
	}

	log.Printf("gateway listening on :%s", port)
	log.Printf("demo bearer token: %s", demoToken)
	log.Printf("runtime base url: %s", envOrDefault("RUNTIME_BASE_URL", "http://127.0.0.1:8001"))
	if err := router.Run(":" + port); err != nil {
		log.Fatalf("run gateway: %v", err)
	}
}

func envOrDefault(key string, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

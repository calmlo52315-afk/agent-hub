package httpapi

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"agenthub/gateway/internal/app"
)

func TestSessionEndpoints(t *testing.T) {
	t.Setenv("GATEWAY_STORE_BACKEND", "memory")
	t.Setenv("RUNTIME_BASE_URL", "http://127.0.0.1:8001")
	repoRoot := filepath.Clean("../../..")
	gatewayApp, demoToken, err := app.New(repoRoot)
	if err != nil {
		t.Fatalf("new app: %v", err)
	}
	defer func() { _ = gatewayApp.Close() }()
	router := NewRouter(gatewayApp)

	body, _ := json.Marshal(map[string]any{
		"title":           "Gateway Session",
		"mode":            "multi_agent",
		"initial_message": "hello gateway",
	})
	req := httptest.NewRequest(http.MethodPost, "/api/v1/sessions", bytes.NewReader(body))
	req.Header.Set("Authorization", "Bearer "+demoToken)
	req.Header.Set("Content-Type", "application/json")
	resp := httptest.NewRecorder()
	router.ServeHTTP(resp, req)
	if resp.Code != http.StatusOK {
		t.Fatalf("create session status=%d body=%s", resp.Code, resp.Body.String())
	}

	listReq := httptest.NewRequest(http.MethodGet, "/api/v1/sessions", nil)
	listReq.Header.Set("Authorization", "Bearer "+demoToken)
	listResp := httptest.NewRecorder()
	router.ServeHTTP(listResp, listReq)
	if listResp.Code != http.StatusOK {
		t.Fatalf("list sessions status=%d body=%s", listResp.Code, listResp.Body.String())
	}
}

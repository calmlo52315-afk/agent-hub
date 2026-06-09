package runtimeclient

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"
)

func TestHTTPClientRunInstruction(t *testing.T) {
	var submitCalls int32
	var pollCalls int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Runtime-Token") != "secret" {
			t.Fatalf("unexpected runtime token")
		}
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/internal/v1/tasks":
			atomic.AddInt32(&submitCalls, 1)
			var payload map[string]any
			if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
				t.Fatalf("decode submit body: %v", err)
			}
			if strings.TrimSpace(payload["instruction"].(string)) == "" {
				t.Fatalf("instruction should not be empty")
			}
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"task_id":"runtime_job_1","status":"queued","poll_after_ms":1}`))
		case r.Method == http.MethodGet && r.URL.Path == "/internal/v1/tasks/runtime_job_1":
			count := atomic.AddInt32(&pollCalls, 1)
			if count == 1 {
				_, _ = w.Write([]byte(`{"task_id":"runtime_job_1","status":"running","completed":false,"poll_after_ms":1,"result":null,"error":null}`))
				return
			}
			_, _ = w.Write([]byte(`{"task_id":"runtime_job_1","status":"completed","completed":true,"poll_after_ms":1,"result":{"ok":true,"task_id":"task_1","trace_id":"trace_1","messages":[],"diagnostics":[],"result":{"coding":{},"coding_subtasks":[],"review":{"agent":"review","role":"review","pass":true,"issues":[],"summary":{}},"artifact":{"agent":"artifact","role":"artifact","artifact_dir":"artifacts/task_1","created_files":[],"summary":{}},"task_plan":{}}},"error":null}`))
		default:
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewHTTPClient(server.URL, "secret", 2*time.Second)
	client.PollInterval = 1 * time.Millisecond
	client.PollTimeout = 1 * time.Second
	result, err := client.RunInstruction(context.Background(), "hello runtime")
	if err != nil {
		t.Fatalf("run instruction: %v", err)
	}
	if !result.OK {
		t.Fatalf("expected ok=true")
	}
	if result.TaskID != "task_1" {
		t.Fatalf("unexpected task id: %s", result.TaskID)
	}
	if atomic.LoadInt32(&submitCalls) != 1 {
		t.Fatalf("expected one submit call")
	}
	if atomic.LoadInt32(&pollCalls) < 2 {
		t.Fatalf("expected poll calls to be issued")
	}
}

func TestHTTPClientCancelTask(t *testing.T) {
	var cancelCalls int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodDelete && r.URL.Path == "/internal/v1/tasks/runtime_job_1" {
			atomic.AddInt32(&cancelCalls, 1)
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"task_id":"runtime_job_1","status":"cancelling","completed":false}`))
			return
		}
		t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
	}))
	defer server.Close()

	client := NewHTTPClient(server.URL, "secret", 2*time.Second)
	if err := client.CancelTask(context.Background(), "runtime_job_1"); err != nil {
		t.Fatalf("cancel task: %v", err)
	}
	if atomic.LoadInt32(&cancelCalls) != 1 {
		t.Fatalf("expected one cancel call")
	}
}

func TestHTTPClientPollTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch {
		case r.Method == http.MethodPost && r.URL.Path == "/internal/v1/tasks":
			w.WriteHeader(http.StatusAccepted)
			_, _ = w.Write([]byte(`{"task_id":"runtime_job_1","status":"queued","poll_after_ms":1}`))
		case r.Method == http.MethodGet && r.URL.Path == "/internal/v1/tasks/runtime_job_1":
			_, _ = w.Write([]byte(`{"task_id":"runtime_job_1","status":"running","completed":false,"poll_after_ms":1,"result":null,"error":null}`))
		default:
			t.Fatalf("unexpected request: %s %s", r.Method, r.URL.Path)
		}
	}))
	defer server.Close()

	client := NewHTTPClient(server.URL, "secret", 2*time.Second)
	client.PollInterval = 1 * time.Millisecond
	client.PollTimeout = 5 * time.Millisecond
	_, err := client.RunInstruction(context.Background(), "hello runtime")
	if err == nil || !errors.Is(err, ErrPollTimeout) {
		t.Fatalf("expected ErrPollTimeout, got %v", err)
	}
}

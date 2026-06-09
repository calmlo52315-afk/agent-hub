package httpapi

import (
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"agenthub/gateway/internal/app"
	"agenthub/gateway/internal/auth"
	"agenthub/gateway/internal/protocol"
	"agenthub/gateway/internal/runtimeclient"
	"agenthub/gateway/internal/store"

	"github.com/gin-gonic/gin"
)

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		origin := c.Request.Header.Get("Origin")
		if origin == "" {
			origin = "*"
		}
		c.Header("Access-Control-Allow-Origin", origin)
		c.Header("Access-Control-Allow-Credentials", "true")
		c.Header("Access-Control-Allow-Headers", "Content-Type, Content-Length, Accept-Encoding, X-CSRF-Token, Authorization, accept, origin, Cache-Control, X-Requested-With")
		c.Header("Access-Control-Allow-Methods", "POST, OPTIONS, GET, PUT, DELETE")

		if c.Request.Method == "OPTIONS" {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}

		c.Next()
	}
}

type createSessionRequest struct {
	Title          string `json:"title"`
	Mode           string `json:"mode"`
	InitialMessage string `json:"initial_message"`
	WorkspaceType  string `json:"workspace_type"`
	SourcePath     string `json:"source_path"`
}

type wsTicketRequest struct {
	SessionID string `json:"session_id"`
}

type workspaceSeedFile struct {
	Path    string `json:"path"`
	Content string `json:"content"`
}

type workspaceSeedRequest struct {
	Files []workspaceSeedFile `json:"files"`
}

type retryTaskRequest struct {
	Reason string `json:"reason"`
	Force  bool   `json:"force"`
}

type cancelTaskRequest struct {
	Reason string `json:"reason"`
}

type approvalDecisionRequest struct {
	Decision string `json:"decision"`
	Reason   string `json:"reason"`
}

type conflictResolutionRequest struct {
	Resolution string `json:"resolution"`
	Reason     string `json:"reason"`
}

// NewRouter 只负责 HTTP / WS 边界，不承载具体业务逻辑。
func NewRouter(gatewayApp *app.GatewayApp) *gin.Engine {
	r := gin.Default()
	r.Use(corsMiddleware())
	r.Use(func(c *gin.Context) {
		c.Set("X-Request-ID", strconv.FormatInt(time.Now().UnixNano(), 10))
		c.Next()
	})
	r.GET("/healthz", func(c *gin.Context) {
		c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"ok": true}})
	})

	authenticated := r.Group("/api/v1")
	authenticated.Use(authMiddleware(gatewayApp))
	{
		authenticated.POST("/sessions", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req createSessionRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			session, err := gatewayApp.CreateSession(principal, req.Title, req.Mode, req.InitialMessage, req.WorkspaceType, req.SourcePath)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: session})
		})

		authenticated.GET("/sessions", func(c *gin.Context) {
			principal := mustPrincipal(c)
			sessions := gatewayApp.ListSessions(principal)
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{
				RequestID: requestID(c),
				Data: gin.H{
					"items":       sessions,
					"next_cursor": nil,
				},
			})
		})

		authenticated.GET("/sessions/:session_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			session, err := gatewayApp.GetSession(principal, c.Param("session_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: session})
		})

		authenticated.PUT("/sessions/:session_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var session store.Session
			if err := c.ShouldBindJSON(&session); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			session.SessionID = c.Param("session_id")
			updatedSession, err := gatewayApp.UpdateSession(principal, session)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: updatedSession})
		})

		authenticated.DELETE("/sessions/:session_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			err := gatewayApp.DeleteSession(principal, c.Param("session_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"deleted": true}})
		})

		authenticated.GET("/sessions/:session_id/messages", func(c *gin.Context) {
			principal := mustPrincipal(c)
			beforeSeq, _ := strconv.ParseInt(c.Query("before_seq"), 10, 64)
			limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
			items, err := gatewayApp.ListSessionMessages(principal, c.Param("session_id"), beforeSeq, limit)
			if err != nil {
				writeAppError(c, err)
				return
			}
			nextBeforeSeq := int64(0)
			if len(items) > 0 {
				nextBeforeSeq = items[len(items)-1].Seq
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{
				RequestID: requestID(c),
				Data: gin.H{
					"items":           items,
					"next_before_seq": nextBeforeSeq,
				},
			})
		})

		authenticated.GET("/sessions/:session_id/tasks", func(c *gin.Context) {
			principal := mustPrincipal(c)
			items, err := gatewayApp.ListSessionTasks(principal, c.Param("session_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"items": items}})
		})

		authenticated.GET("/sessions/:session_id/artifacts", func(c *gin.Context) {
			principal := mustPrincipal(c)
			items, err := gatewayApp.ListSessionArtifacts(principal, c.Param("session_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"items": items}})
		})

		authenticated.GET("/tasks/:task_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			task, err := gatewayApp.GetTask(principal, c.Param("task_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: task})
		})

		authenticated.POST("/tasks/:task_id/retry", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req retryTaskRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			data, err := gatewayApp.RequestTaskRetry(principal, c.Param("task_id"), req.Reason, req.Force)
			if err != nil && !errors.Is(err, app.ErrApprovalRequired) {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: data})
		})

		authenticated.POST("/tasks/:task_id/cancel", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req cancelTaskRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			if err := gatewayApp.CancelTask(principal, c.Param("task_id"), req.Reason); err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"task_id": c.Param("task_id"), "status": "cancelled"}})
		})

		authenticated.POST("/tasks/:task_id/approvals/:approval_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req approvalDecisionRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			data, err := gatewayApp.SubmitApproval(principal, c.Param("task_id"), c.Param("approval_id"), req.Decision, req.Reason)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: data})
		})

		authenticated.POST("/tasks/:task_id/conflicts/:conflict_id/resolve", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req conflictResolutionRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			data, err := gatewayApp.ResolveConflict(principal, c.Param("task_id"), c.Param("conflict_id"), req.Resolution, req.Reason)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: data})
		})

		authenticated.GET("/artifacts/:artifact_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			card, err := gatewayApp.GetArtifact(principal, c.Param("artifact_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: card})
		})

		authenticated.POST("/ws-tickets", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req wsTicketRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			ticket, expiresAt, err := gatewayApp.IssueWSTicket(principal, req.SessionID)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{
				RequestID: requestID(c),
				Data: gin.H{
					"session_id": req.SessionID,
					"ws_ticket":  ticket,
					"expires_at": expiresAt,
				},
			})
		})

		authenticated.GET("/fs/list", func(c *gin.Context) {
			requestPath := c.DefaultQuery("path", "/")

			// Clean the path to prevent traversal attacks
			cleanPath := filepath.Clean(requestPath)

			entries, err := os.ReadDir(cleanPath)
			if err != nil {
				writeError(c, http.StatusBadRequest, "fs_error", err.Error())
				return
			}

			directories := make([]string, 0)
			for _, e := range entries {
				if e.IsDir() && !strings.HasPrefix(e.Name(), ".") {
					directories = append(directories, e.Name())
				}
			}

			// Determine parent path
			parent := filepath.Dir(cleanPath)
			if parent == cleanPath {
				parent = ""
			}

			c.JSON(http.StatusOK, protocol.HTTPEnvelope{
				RequestID: requestID(c),
				Data: gin.H{
					"path":        cleanPath,
					"parent":      parent,
					"directories": directories,
				},
			})
		})

		authenticated.GET("/sessions/:session_id/workspace/files", func(c *gin.Context) {
			principal := mustPrincipal(c)
			files, err := gatewayApp.GetWorkspaceFiles(principal, c.Param("session_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: files})
		})

			// GET /workspace/file?path= — 按需加载单个文件内容（懒加载，VSCode 模式）
			authenticated.GET("/sessions/:session_id/workspace/file", func(c *gin.Context) {
				principal := mustPrincipal(c)
				filePath := c.Query("path")
				if filePath == "" {
					writeError(c, http.StatusBadRequest, "invalid_request", "path query parameter required")
					return
				}
				result, err := gatewayApp.ReadWorkspaceFile(principal, c.Param("session_id"), filePath)
				if err != nil {
					writeAppError(c, err)
					return
				}
				c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: result})
			})

			authenticated.POST("/sessions/:session_id/workspace/seed", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req workspaceSeedRequest
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			files := make([]runtimeclient.WorkspaceSeedFile, len(req.Files))
			for i, f := range req.Files {
				files[i] = runtimeclient.WorkspaceSeedFile{Path: f.Path, Content: f.Content}
			}
			result, err := gatewayApp.SeedWorkspace(principal, c.Param("session_id"), files)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: result})
		})

		authenticated.POST("/sessions/:session_id/workspace/files-content", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req struct {
				Paths []string `json:"paths"`
			}
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			result, err := gatewayApp.ReadWorkspaceFilesContent(principal, c.Param("session_id"), req.Paths)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: result})
		})

		// ── Agent Definitions ───────────────────────────────

		authenticated.POST("/agents", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req store.AgentDefinitionRecord
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			record, err := gatewayApp.CreateAgentDefinition(principal, req)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: record})
		})

		authenticated.GET("/agents", func(c *gin.Context) {
			principal := mustPrincipal(c)
			items := gatewayApp.ListAgentDefinitions(principal)
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"items": items}})
		})

		authenticated.GET("/agents/marketplace", func(c *gin.Context) {
			items := gatewayApp.ListPublicAgentDefinitions()
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"items": items}})
		})

		authenticated.GET("/agents/:agent_id", func(c *gin.Context) {
			record, err := gatewayApp.GetAgentDefinition(c.Param("agent_id"))
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: record})
		})

		authenticated.PUT("/agents/:agent_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			var req store.AgentDefinitionRecord
			if err := c.ShouldBindJSON(&req); err != nil {
				writeError(c, http.StatusBadRequest, "invalid_request", err.Error())
				return
			}
			req.ID = c.Param("agent_id")
			record, err := gatewayApp.UpdateAgentDefinition(principal, req)
			if err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: record})
		})

		authenticated.DELETE("/agents/:agent_id", func(c *gin.Context) {
			principal := mustPrincipal(c)
			if err := gatewayApp.DeleteAgentDefinition(principal, c.Param("agent_id")); err != nil {
				writeAppError(c, err)
				return
			}
			c.JSON(http.StatusOK, protocol.HTTPEnvelope{RequestID: requestID(c), Data: gin.H{"deleted": true}})
		})
	}

	r.GET("/ws", func(c *gin.Context) {
		ticket := c.Query("ticket")
		principal, sessionID, err := gatewayApp.Auth.ConsumeWSTicket(ticket)
		if err != nil {
			c.JSON(http.StatusUnauthorized, protocol.HTTPEnvelope{RequestID: requestID(c), Error: &protocol.HTTPError{Code: "unauthorized", Message: "invalid ws ticket"}})
			return
		}
		if err := gatewayApp.Hub.Handle(c, sessionID, principal.ID, gatewayApp.HandleWSCommand); err != nil {
			c.JSON(http.StatusBadRequest, protocol.HTTPEnvelope{RequestID: requestID(c), Error: &protocol.HTTPError{Code: "ws_upgrade_failed", Message: err.Error()}})
		}
	})

	return r
}

func authMiddleware(gatewayApp *app.GatewayApp) gin.HandlerFunc {
	return func(c *gin.Context) {
		principal, err := gatewayApp.Auth.AuthenticateBearer(c.GetHeader("Authorization"))
		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, protocol.HTTPEnvelope{
				RequestID: requestID(c),
				Error: &protocol.HTTPError{
					Code:    "unauthorized",
					Message: "missing or invalid bearer token",
				},
			})
			return
		}
		c.Set("principal", principal)
		c.Next()
	}
}

func mustPrincipal(c *gin.Context) auth.Principal {
	value, _ := c.Get("principal")
	principal, _ := value.(auth.Principal)
	return principal
}

func writeAppError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, auth.ErrUnauthorized):
		writeError(c, http.StatusUnauthorized, "unauthorized", err.Error())
	case errors.Is(err, store.ErrSessionForbidden):
		writeError(c, http.StatusForbidden, "session_forbidden", err.Error())
	case errors.Is(err, store.ErrNotFound):
		writeError(c, http.StatusNotFound, "not_found", err.Error())
	default:
		writeError(c, http.StatusBadRequest, "bad_request", err.Error())
	}
}

func writeError(c *gin.Context, status int, code, message string) {
	c.JSON(status, protocol.HTTPEnvelope{
		RequestID: requestID(c),
		Error: &protocol.HTTPError{
			Code:    code,
			Message: message,
		},
	})
}

func requestID(c *gin.Context) string {
	return c.GetString("X-Request-ID")
}

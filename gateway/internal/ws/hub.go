package ws

import (
	"crypto/rand"
	"encoding/hex"
	"log"
	"net/http"
	"sync"
	"time"

	"agenthub/gateway/internal/protocol"
	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

// Client 代表一个 session 级 WebSocket 连接。
type Client struct {
	Conn        *websocket.Conn
	SessionID   string
	PrincipalID string
	Subscribed  bool
	send        chan protocol.WSEvent
}

// Hub 负责管理连接、广播和点对点回放发送。
type Hub struct {
	mu       sync.RWMutex
	clients  map[string]map[*Client]struct{}
	upgrader websocket.Upgrader
}

func NewHub() *Hub {
	return &Hub{
		clients: make(map[string]map[*Client]struct{}),
		upgrader: websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool { return true },
		},
	}
}

func (h *Hub) Handle(c *gin.Context, sessionID, principalID string, onEvent func(*Client, protocol.WSEvent)) error {
	conn, err := h.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		return err
	}

	client := &Client{
		Conn:        conn,
		SessionID:   sessionID,
		PrincipalID: principalID,
		send:        make(chan protocol.WSEvent, 32),
	}
	h.register(client)
	go h.writeLoop(client)
	go h.readLoop(client, onEvent)
	return nil
}

func (h *Hub) Send(client *Client, event protocol.WSEvent) {
	select {
	case client.send <- event:
	default:
		log.Printf("ws send buffer full for session=%s principal=%s", client.SessionID, client.PrincipalID)
	}
}

func (h *Hub) Broadcast(sessionID string, event protocol.WSEvent) {
	h.mu.RLock()
	defer h.mu.RUnlock()
	for client := range h.clients[sessionID] {
		if !client.Subscribed {
			continue
		}
		select {
		case client.send <- event:
		default:
			log.Printf("ws broadcast buffer full for session=%s", sessionID)
		}
	}
}

func (h *Hub) MarkSubscribed(client *Client) {
	client.Subscribed = true
}

func (h *Hub) Replay(client *Client, events []protocol.WSEvent) {
	for _, event := range events {
		event.Status = "replayed"
		h.Send(client, event)
	}
}

func (h *Hub) register(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if _, ok := h.clients[client.SessionID]; !ok {
		h.clients[client.SessionID] = make(map[*Client]struct{})
	}
	h.clients[client.SessionID][client] = struct{}{}
}

func (h *Hub) unregister(client *Client) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if clients, ok := h.clients[client.SessionID]; ok {
		delete(clients, client)
		if len(clients) == 0 {
			delete(h.clients, client.SessionID)
		}
	}
	close(client.send)
	_ = client.Conn.Close()
}

func (h *Hub) readLoop(client *Client, onEvent func(*Client, protocol.WSEvent)) {
	defer h.unregister(client)
	for {
		var event protocol.WSEvent
		if err := client.Conn.ReadJSON(&event); err != nil {
			return
		}
		if event.SessionID == "" {
			event.SessionID = client.SessionID
		}
		onEvent(client, event)
	}
}

func (h *Hub) writeLoop(client *Client) {
	ticker := time.NewTicker(25 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case event, ok := <-client.send:
			if !ok {
				return
			}
			if err := client.Conn.WriteJSON(event); err != nil {
				return
			}
		case <-ticker.C:
			heartbeat := protocol.WSEvent{
				SchemaVersion: "1.0",
				EventID:       newEventID(),
				SessionID:     client.SessionID,
				Type:          "heartbeat",
				Kind:          "event",
				Timestamp:     protocol.NowISO(),
				Sender:        protocol.Party{Type: "gateway", ID: "gateway"},
				Receiver:      protocol.Party{Type: "frontend", ID: client.PrincipalID},
				Status:        "success",
				Payload:       map[string]any{"alive": true},
			}
			if err := client.Conn.WriteJSON(heartbeat); err != nil {
				return
			}
		}
	}
}

func newEventID() string {
	buf := make([]byte, 8)
	_, _ = rand.Read(buf)
	return "evt_" + hex.EncodeToString(buf)
}

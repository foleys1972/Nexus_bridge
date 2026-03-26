import type { WebSocketServer } from "ws";
import { WebSocket, type RawData } from "ws";
import crypto from "node:crypto";
import type { IncomingMessage } from "node:http";
import type { Db } from "../lib/db.js";
import type { AppConfig } from "../lib/config.js";

type ClientInfo = {
  id: string;
  ip?: string;
  connectedAt: string;
  subscriptions: Array<{ channel: string; site_id: string }>;
};

const clients = new Map<WebSocket, ClientInfo>();

export function getClientSnapshot() {
  return {
    clients: Array.from(clients.values())
  };
}

export function attachClientProxy(opts: { wss: WebSocketServer; db: Db; config: AppConfig }): void {
  const { wss } = opts;

  wss.on("connection", (ws: WebSocket, req: IncomingMessage) => {
    const id = crypto.randomUUID();
    const info: ClientInfo = {
      id,
      ip: req.socket.remoteAddress,
      connectedAt: new Date().toISOString(),
      subscriptions: []
    };
    clients.set(ws, info);

    ws.on("message", (data: RawData) => {
      let msg: any;
      try {
        msg = JSON.parse(data.toString("utf8"));
      } catch {
        ws.send(JSON.stringify({ type: "error", error: "malformed_json" }));
        return;
      }

      if (msg?.action === "subscribe") {
        const channel = String(msg.channel ?? "");
        const siteId = String(msg.site_id ?? "");
        info.subscriptions.push({ channel, site_id: siteId });
        ws.send(JSON.stringify({ type: "subscribed", channel, site_id: siteId }));
        return;
      }

      ws.send(JSON.stringify({ type: "error", error: "unknown_action" }));
    });

    ws.on("close", () => {
      clients.delete(ws);
    });
  });
}
